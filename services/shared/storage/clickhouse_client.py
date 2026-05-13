from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from typing import Any

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

from services.shared.kafka.serialization import serialize_json

logger = logging.getLogger(__name__)


class ClickHouseSettings(BaseSettings):
    clickhouse_host: str = "localhost"
    clickhouse_http_port: int = 8123
    clickhouse_database: str = "cascade"
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_timeout_seconds: float = 10.0

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    @property
    def base_url(self) -> str:
        return f"http://{self.clickhouse_host}:{self.clickhouse_http_port}"


class ClickHouseClient:
    def __init__(self, settings: ClickHouseSettings | None = None) -> None:
        self.settings = settings or ClickHouseSettings()

    async def ping(self) -> bool:
        try:
            text = await self.fetch_text("SELECT 1")
            return text.strip() == "1"
        except Exception as exc:
            logger.warning("ClickHouse ping failed: %s", exc)
            return False

    async def execute(self, query: str) -> str:
        async with httpx.AsyncClient(timeout=self.settings.clickhouse_timeout_seconds) as client:
            response = await client.post(
                self.settings.base_url,
                params=self._auth_params(query),
                content=b"",
            )
            response.raise_for_status()
            return response.text

    async def fetch_text(self, query: str) -> str:
        async with httpx.AsyncClient(timeout=self.settings.clickhouse_timeout_seconds) as client:
            response = await client.get(self.settings.base_url, params=self._auth_params(query))
            response.raise_for_status()
            return response.text

    async def fetch_json_rows(self, query: str) -> list[dict[str, Any]]:
        text = await self.fetch_text(query.rstrip(";") + " FORMAT JSONEachRow")
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            if line.strip():
                rows.append(httpx.Response(200, content=line).json())
        return rows

    async def initialize_schema(self) -> None:
        for statement in schema_statements(self.settings.clickhouse_database):
            await self.execute(statement)

    async def insert_rows(self, table: str, rows: Iterable[dict[str, Any]]) -> int:
        materialized = list(rows)
        if not materialized:
            return 0
        payload = b"\n".join(serialize_json(row) for row in materialized)
        query = f"INSERT INTO {self.settings.clickhouse_database}.{table} FORMAT JSONEachRow"
        await self._with_retry(lambda: self._post(query, payload))
        logger.info("Inserted ClickHouse rows table=%s count=%s", table, len(materialized))
        return len(materialized)

    async def recent_telemetry(self, limit: int = 20, service: str | None = None, namespace: str | None = None, event_type: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"service": service, "namespace": namespace, "event_type": event_type})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.telemetry_events {where} ORDER BY observed_at DESC LIMIT {self._limit(limit)}")

    async def service_history(self, service: str, limit: int = 50) -> list[dict[str, Any]]:
        safe = self._quote(service)
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.telemetry_events WHERE service = {safe} ORDER BY observed_at DESC LIMIT {self._limit(limit)}")

    async def recent_experiments(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.experiment_events ORDER BY observed_at DESC LIMIT {self._limit(limit)}")

    async def recent_incidents(self, limit: int = 20, service: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"root_cause_service": service})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.incidents {where} ORDER BY first_seen_at DESC LIMIT {self._limit(limit)}")

    async def incident_with_reports(self, incident_id: str) -> dict[str, Any]:
        safe = self._quote(incident_id)
        incidents = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.incidents WHERE incident_id = {safe} ORDER BY created_at DESC LIMIT 1")
        reports = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.incident_reports WHERE incident_id = {safe} ORDER BY generated_at DESC LIMIT 5")
        return {"incident": incidents[0] if incidents else None, "reports": reports}

    async def latest_topology_snapshot(self) -> dict[str, Any] | None:
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.topology_snapshots ORDER BY captured_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def recent_feature_windows(self, limit: int = 20, service: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"service": service})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.telemetry_feature_windows {where} ORDER BY window_end DESC LIMIT {self._limit(limit)}")

    async def recent_anomalies(self, limit: int = 20, service: str | None = None, severity: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"service": service, "severity": severity})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.anomaly_events {where} ORDER BY detected_at DESC LIMIT {self._limit(limit)}")

    async def service_anomalies(self, service: str, limit: int = 50) -> list[dict[str, Any]]:
        safe = self._quote(service)
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.anomaly_events WHERE service = {safe} ORDER BY detected_at DESC LIMIT {self._limit(limit)}")

    async def anomaly_detail(self, anomaly_id: str) -> dict[str, Any] | None:
        safe = self._quote(anomaly_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.anomaly_events WHERE anomaly_id = {safe} ORDER BY detected_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def count(self, table: str) -> int:
        text = await self.fetch_text(f"SELECT count() FROM {self.settings.clickhouse_database}.{table}")
        return int(text.strip() or "0")

    async def _post(self, query: str, payload: bytes) -> None:
        async with httpx.AsyncClient(timeout=self.settings.clickhouse_timeout_seconds) as client:
            response = await client.post(
                self.settings.base_url,
                params=self._auth_params(query),
                content=payload,
                headers={"Content-Type": "application/x-ndjson"},
            )
            response.raise_for_status()

    async def _with_retry(self, action, attempts: int = 5) -> None:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                await action()
                return
            except Exception as exc:
                last_error = exc
                logger.warning("ClickHouse operation failed attempt=%s/%s error=%s", attempt, attempts, exc)
                await asyncio.sleep(attempt)
        raise RuntimeError("ClickHouse operation failed") from last_error

    def _auth_params(self, query: str) -> dict[str, str]:
        params = {"query": query, "user": self.settings.clickhouse_user}
        if self.settings.clickhouse_password:
            params["password"] = self.settings.clickhouse_password
        return params

    @staticmethod
    def _limit(limit: int) -> int:
        return max(1, min(int(limit), 500))

    @staticmethod
    def _quote(value: str) -> str:
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"

    def _where(self, filters: dict[str, str | None]) -> str:
        clauses = [f"{key} = {self._quote(value)}" for key, value in filters.items() if value]
        return "WHERE " + " AND ".join(clauses) if clauses else ""


def schema_statements(database: str = "cascade") -> list[str]:
    db = database
    return [
        f"CREATE DATABASE IF NOT EXISTS {db}",
        f"""
CREATE TABLE IF NOT EXISTS {db}.telemetry_events (
    event_id String,
    observed_at DateTime64(3),
    ingested_at DateTime64(3),
    source_topic String,
    event_type String,
    namespace String,
    service String,
    workload String,
    pod String,
    severity String,
    health_status String,
    experiment_id String,
    trace_id String,
    raw_json String,
    enriched_json String,
    labels_json String,
    numeric_features_json String
) ENGINE = MergeTree
ORDER BY (service, observed_at, event_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.experiment_events (
    event_id String,
    experiment_id String,
    experiment_type String,
    target_namespace String,
    target_service String,
    target_workload String,
    status String,
    started_at DateTime64(3),
    completed_at Nullable(DateTime64(3)),
    observed_at DateTime64(3),
    ingested_at DateTime64(3),
    source_topic String,
    event_json String
) ENGINE = MergeTree
ORDER BY (experiment_id, observed_at, event_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.incidents (
    incident_id String,
    experiment_id String,
    root_cause_service String,
    root_cause_summary String,
    severity String,
    status String,
    confidence Float64,
    first_seen_at DateTime64(3),
    last_seen_at DateTime64(3),
    created_at DateTime64(3),
    affected_services_json String,
    causal_chain_json String,
    evidence_json String,
    incident_json String
) ENGINE = MergeTree
ORDER BY (root_cause_service, first_seen_at, incident_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.incident_reports (
    report_id String,
    incident_id String,
    experiment_id String,
    generated_at DateTime64(3),
    root_cause_service String,
    severity String,
    markdown_report String,
    report_json String
) ENGINE = MergeTree
ORDER BY (root_cause_service, generated_at, report_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.topology_snapshots (
    snapshot_id String,
    captured_at DateTime64(3),
    topology_json String,
    service_count UInt64,
    edge_count UInt64
) ENGINE = MergeTree
ORDER BY (captured_at, snapshot_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.telemetry_feature_windows (
    window_id String,
    service String,
    namespace String,
    workload String,
    window_start DateTime64(3),
    window_end DateTime64(3),
    extracted_at DateTime64(3),
    event_count UInt64,
    unhealthy_count UInt64,
    healthy_count UInt64,
    restart_signal_count UInt64,
    warning_count UInt64,
    error_count UInt64,
    experiment_event_count UInt64,
    incident_context_count UInt64,
    avg_cpu Float64,
    max_cpu Float64,
    avg_memory Float64,
    max_memory Float64,
    avg_latency_ms Float64,
    max_latency_ms Float64,
    error_rate Float64,
    restart_rate Float64,
    unhealthy_rate Float64,
    feature_vector_json String,
    source_query_hash String
) ENGINE = MergeTree
ORDER BY (service, window_start, window_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.anomaly_events (
    anomaly_id String,
    detected_at DateTime64(3),
    window_id String,
    service String,
    namespace String,
    workload String,
    window_start DateTime64(3),
    window_end DateTime64(3),
    severity String,
    status String,
    anomaly_score Float64,
    risk_score Float64,
    model_name String,
    model_version String,
    detector_type String,
    is_anomaly UInt8,
    explanation String,
    evidence_json String,
    feature_vector_json String,
    related_experiment_id String,
    published_to_redpanda UInt8
) ENGINE = MergeTree
ORDER BY (service, detected_at, anomaly_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.model_runs (
    run_id String,
    started_at DateTime64(3),
    completed_at DateTime64(3),
    model_name String,
    model_version String,
    detector_type String,
    windows_scored UInt64,
    anomalies_detected UInt64,
    status String,
    config_json String,
    error_message String
) ENGINE = MergeTree
ORDER BY (started_at, run_id)
""",
    ]
