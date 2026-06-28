from __future__ import annotations

import asyncio
import logging
import json
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
        await self._wait_until_ready()
        for statement in schema_statements(self.settings.clickhouse_database):
            await self._with_retry(lambda stmt=statement: self.execute(stmt))

    async def _wait_until_ready(self, attempts: int = 20, delay: float = 1.5) -> None:
        for attempt in range(1, attempts + 1):
            if await self.ping():
                return
            logger.warning("Waiting for ClickHouse readiness attempt=%s/%s", attempt, attempts)
            await asyncio.sleep(delay)
        raise RuntimeError(f"ClickHouse not ready after {attempts} attempts")

    async def insert_rows(self, table: str, rows: Iterable[dict[str, Any]]) -> int:
        materialized = list(rows)
        if not materialized:
            return 0
        payload = b"\n".join(serialize_json(row) for row in materialized)
        query = f"INSERT INTO {self.settings.clickhouse_database}.{table} FORMAT JSONEachRow"
        await self._with_retry(lambda: self._post(query, payload))
        logger.info("Inserted ClickHouse rows table=%s count=%s", table, len(materialized))
        return len(materialized)

    async def insert_audit_event(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("audit_events", [row])

    async def recent_audit_events(
        self,
        limit: int = 100,
        subsystem: str | None = None,
        severity: str | None = None,
        service: str | None = None,
        namespace: str | None = None,
        status: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        correlation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        where = self._audit_where(
            {
                "subsystem": subsystem,
                "severity": severity,
                "service": service,
                "namespace": namespace,
                "status": status,
                "correlation_id": correlation_id,
            },
            start_time,
            end_time,
        )
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.audit_events {where} ORDER BY timestamp DESC LIMIT {self._limit(limit)}")

    async def audit_event(self, event_id: str) -> dict[str, Any] | None:
        safe = self._quote(event_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.audit_events WHERE event_id = {safe} ORDER BY timestamp DESC LIMIT 1")
        return rows[0] if rows else None

    async def audit_timeline(self, correlation_id: str, limit: int = 200) -> list[dict[str, Any]]:
        safe = self._quote(correlation_id)
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.audit_events WHERE correlation_id = {safe} OR run_id = {safe} OR autopilot_run_id = {safe} ORDER BY timestamp ASC LIMIT {self._limit(limit)}")

    async def audit_service_timeline(self, namespace: str, service: str, limit: int = 200) -> list[dict[str, Any]]:
        where = self._where({"namespace": namespace, "service": service})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.audit_events {where} ORDER BY timestamp ASC LIMIT {self._limit(limit)}")

    async def audit_autopilot_timeline(self, run_id: str, limit: int = 200) -> list[dict[str, Any]]:
        safe = self._quote(run_id)
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.audit_events WHERE autopilot_run_id = {safe} OR run_id = {safe} OR correlation_id = {safe} ORDER BY timestamp ASC LIMIT {self._limit(limit)}")

    async def insert_anomaly_events(self, rows: Iterable[dict[str, Any]]) -> int:
        materialized = list(rows)
        if not materialized:
            return 0
        existing = await self.existing_anomaly_ids([str(row.get("anomaly_id") or "") for row in materialized])
        seen = set(existing)
        new_rows = []
        for row in materialized:
            anomaly_id = str(row.get("anomaly_id") or "")
            if not anomaly_id or anomaly_id in seen:
                continue
            seen.add(anomaly_id)
            new_rows.append(row)
        return await self.insert_rows("anomaly_events", new_rows)

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

    async def existing_anomaly_ids(self, anomaly_ids: list[str]) -> set[str]:
        cleaned = sorted({item for item in anomaly_ids if item})
        if not cleaned:
            return set()
        values = ", ".join(self._quote(item) for item in cleaned)
        rows = await self.fetch_json_rows(f"SELECT DISTINCT anomaly_id FROM {self.settings.clickhouse_database}.anomaly_events WHERE anomaly_id IN ({values})")
        return {str(row["anomaly_id"]) for row in rows}

    async def insert_causal_report(self, report: dict[str, Any]) -> int:
        report_row = {
            "report_id": str(report.get("report_id") or ""),
            "generated_at": str(report.get("generated_at") or ""),
            "target_service": str(report.get("target_service") or ""),
            "target_feature": str(report.get("target_feature") or ""),
            "source_feature": str(report.get("source_feature") or ""),
            "status": str(report.get("status") or ""),
            "summary": str(report.get("summary") or ""),
            "window_start": report.get("window_start"),
            "window_end": report.get("window_end"),
            "candidate_count": len(report.get("candidates") or []),
            "methodology_json": self.json_dumps(report.get("methodology") or {}),
            "limitations_json": self.json_dumps(report.get("limitations") or []),
            "report_json": self.json_dumps(report),
        }
        candidate_rows = []
        for candidate in report.get("candidates") or []:
            candidate_rows.append({
                "report_id": report_row["report_id"],
                "candidate_id": f"{report_row['report_id']}:{candidate.get('source_service', '')}:{candidate.get('lag_windows', 0)}",
                "generated_at": report_row["generated_at"],
                "rank": int(candidate.get("rank") or 0),
                "source_service": str(candidate.get("source_service") or ""),
                "target_service": str(candidate.get("target_service") or ""),
                "source_feature": str(candidate.get("source_feature") or ""),
                "target_feature": str(candidate.get("target_feature") or ""),
                "status": str(candidate.get("status") or ""),
                "rank_score": float(candidate.get("rank_score") or 0.0),
                "best_p_value": candidate.get("best_p_value"),
                "effect_size": float(candidate.get("effect_size") or 0.0),
                "lag_windows": int(candidate.get("lag_windows") or 0),
                "sample_count": int(candidate.get("sample_count") or 0),
                "pearson_json": self.json_dumps(candidate.get("pearson") or {}),
                "spearman_json": self.json_dumps(candidate.get("spearman") or {}),
                "granger_json": self.json_dumps(candidate.get("granger") or {}),
                "topology_distance": candidate.get("topology_distance"),
                "anomaly_context_json": self.json_dumps(candidate.get("anomaly_context") or {}),
                "limitations_json": self.json_dumps(candidate.get("limitations") or []),
                "candidate_json": self.json_dumps(candidate),
            })
        inserted = await self.insert_rows("causal_reports", [report_row])
        inserted += await self.insert_rows("causal_candidates", candidate_rows)
        return inserted

    async def recent_causal_reports(self, limit: int = 20, target_service: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"target_service": target_service})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.causal_reports {where} ORDER BY generated_at DESC LIMIT {self._limit(limit)}")

    async def causal_report_detail(self, report_id: str) -> dict[str, Any]:
        safe = self._quote(report_id)
        reports = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.causal_reports WHERE report_id = {safe} ORDER BY generated_at DESC LIMIT 1")
        candidates = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.causal_candidates WHERE report_id = {safe} ORDER BY rank ASC LIMIT 200")
        return {"report": reports[0] if reports else None, "candidates": candidates}

    async def insert_rca_report(self, report: dict[str, Any]) -> int:
        row = {
            "report_id": str(report.get("report_id") or ""),
            "generated_at": str(report.get("generated_at") or ""),
            "status": str(report.get("status") or ""),
            "target_service": str(report.get("target_service") or ""),
            "likely_root_cause_service": str(report.get("likely_root_cause_service") or ""),
            "confidence_score": float(report.get("confidence_score") or 0.0),
            "affected_services_json": self.json_dumps(report.get("affected_downstream_services") or []),
            "related_chaos_json": self.json_dumps(report.get("related_chaos_experiment") or {}),
            "evidence_json": self.json_dumps(report.get("evidence") or []),
            "timeline_json": self.json_dumps(report.get("timeline") or []),
            "limitations_json": self.json_dumps(report.get("limitations") or []),
            "explanation": str(report.get("explanation") or ""),
            "report_json": self.json_dumps(report),
        }
        return await self.insert_rows("rca_reports", [row])

    async def recent_rca_reports(self, limit: int = 20, service: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"target_service": service})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.rca_reports {where} ORDER BY generated_at DESC LIMIT {self._limit(limit)}")

    async def rca_report_detail(self, report_id: str) -> dict[str, Any] | None:
        safe = self._quote(report_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.rca_reports WHERE report_id = {safe} ORDER BY generated_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def count(self, table: str) -> int:
        text = await self.fetch_text(f"SELECT count() FROM {self.settings.clickhouse_database}.{table}")
        return int(text.strip() or "0")

    async def table_exists(self, table: str) -> bool:
        safe = self._quote(table)
        text = await self.fetch_text(f"SELECT count() FROM system.tables WHERE database = {self._quote(self.settings.clickhouse_database)} AND name = {safe}")
        return int(text.strip() or "0") > 0

    async def insert_knowledge_documents(self, rows: Iterable[dict[str, Any]]) -> int:
        return await self.insert_rows("knowledge_documents", rows)

    async def insert_knowledge_chunks(self, rows: Iterable[dict[str, Any]]) -> int:
        return await self.insert_rows("knowledge_chunks", rows)

    async def insert_knowledge_ingestion_run(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("knowledge_ingestion_runs", [row])

    async def insert_knowledge_query(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("knowledge_queries", [row])

    async def knowledge_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        if not chunk_ids:
            return []
        values = ", ".join(self._quote(item) for item in chunk_ids)
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.knowledge_chunks WHERE chunk_id IN ({values})")

    async def existing_knowledge_document_ids(self, document_ids: list[str]) -> set[str]:
        if not document_ids:
            return set()
        values = ", ".join(self._quote(item) for item in document_ids)
        rows = await self.fetch_json_rows(f"SELECT DISTINCT document_id FROM {self.settings.clickhouse_database}.knowledge_documents WHERE document_id IN ({values})")
        return {str(row["document_id"]) for row in rows}

    async def existing_knowledge_chunk_ids(self, chunk_ids: list[str]) -> set[str]:
        if not chunk_ids:
            return set()
        values = ", ".join(self._quote(item) for item in chunk_ids)
        rows = await self.fetch_json_rows(f"SELECT DISTINCT chunk_id FROM {self.settings.clickhouse_database}.knowledge_chunks WHERE chunk_id IN ({values})")
        return {str(row["chunk_id"]) for row in rows}

    async def recent_knowledge_documents(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.knowledge_documents ORDER BY updated_at DESC LIMIT {self._limit(limit)}")

    async def recent_knowledge_chunks(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.knowledge_chunks ORDER BY ingested_at DESC LIMIT {self._limit(limit)}")

    async def recent_knowledge_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.knowledge_ingestion_runs ORDER BY started_at DESC LIMIT {self._limit(limit)}")

    async def recent_incident_reports_for_knowledge(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.incident_reports ORDER BY generated_at DESC LIMIT {self._limit(limit)}")

    async def recent_topology_snapshots(self, limit: int = 10) -> list[dict[str, Any]]:
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.topology_snapshots ORDER BY captured_at DESC LIMIT {self._limit(limit)}")

    async def knowledge_stats(self) -> dict[str, int | None]:
        stats: dict[str, int | None] = {}
        for table in ["knowledge_documents", "knowledge_chunks", "knowledge_ingestion_runs", "knowledge_queries"]:
            try:
                stats[table] = await self.count(table)
            except Exception:
                stats[table] = None
        return stats

    async def insert_investigation_run(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("investigation_runs", [row])

    async def insert_agent_step(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("agent_steps", [row])

    async def insert_agent_tool_call(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("agent_tool_calls", [row])

    async def insert_investigation_report(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("investigation_reports", [row])

    async def recent_investigation_runs(self, limit: int = 20, service: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"service": service, "status": status})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.investigation_runs {where} ORDER BY created_at DESC LIMIT {self._limit(limit)}")

    async def investigation_detail(self, investigation_id: str) -> dict[str, Any]:
        safe = self._quote(investigation_id)
        runs = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.investigation_runs WHERE investigation_id = {safe} ORDER BY updated_at DESC LIMIT 1")
        steps = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.agent_steps WHERE investigation_id = {safe} ORDER BY created_at ASC LIMIT 200")
        reports = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.investigation_reports WHERE investigation_id = {safe} ORDER BY generated_at DESC LIMIT 1")
        calls = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.agent_tool_calls WHERE investigation_id = {safe} ORDER BY called_at ASC LIMIT 200")
        return {"run": runs[0] if runs else None, "steps": steps, "tool_calls": calls, "report": reports[0] if reports else None}

    async def agent_stats(self) -> dict[str, int | None]:
        stats: dict[str, int | None] = {}
        for table in ["investigation_runs", "agent_steps", "investigation_reports", "agent_tool_calls"]:
            try:
                stats[table] = await self.count(table)
            except Exception:
                stats[table] = None
        return stats

    async def insert_chaos_experiment_plan(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("chaos_experiment_plans", [row])

    async def insert_chaos_experiment_run(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("chaos_experiment_runs", [row])

    async def insert_chaos_observation(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("chaos_observations", [row])

    async def insert_resilience_score(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("resilience_scores", [row])

    async def insert_chaos_safety_violation(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("chaos_safety_violations", [row])

    async def insert_chaos_policy_audit(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("chaos_policy_audit", [row])

    async def insert_chaos_campaign(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("chaos_campaigns", [row])

    async def insert_chaos_campaign_run(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("chaos_campaign_runs", [row])

    async def insert_chaos_campaign_step(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("chaos_campaign_steps", [row])

    async def recent_chaos_plans(self, limit: int = 20, service: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"target_service": service, "status": status})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.chaos_experiment_plans {where} ORDER BY created_at DESC LIMIT {self._limit(limit)}")

    async def chaos_plan(self, plan_id: str) -> dict[str, Any] | None:
        safe = self._quote(plan_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.chaos_experiment_plans WHERE plan_id = {safe} ORDER BY updated_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def recent_chaos_runs(self, limit: int = 20, service: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        return await self.fetch_json_rows(f"{self._latest_chaos_runs_query({'target_service': service, 'status': status})} ORDER BY latest_state_at DESC LIMIT {self._limit(limit)}")

    async def chaos_run_detail(self, run_id: str) -> dict[str, Any]:
        safe = self._quote(run_id)
        runs = await self.fetch_json_rows(f"{self._latest_chaos_runs_query({'run_id': run_id})} LIMIT 1")
        observations = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.chaos_observations WHERE run_id = {safe} ORDER BY observed_at DESC LIMIT 1")
        scores = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.resilience_scores WHERE run_id = {safe} ORDER BY computed_at DESC LIMIT 1")
        return {"run": runs[0] if runs else None, "observation": observations[0] if observations else None, "score": scores[0] if scores else None}

    async def latest_chaos_dry_run(self, plan_id: str) -> dict[str, Any] | None:
        rows = await self.fetch_json_rows(f"{self._latest_chaos_runs_query({'plan_id': plan_id})} AND dry_run = 1 AND status = 'dry_run' ORDER BY latest_state_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def recent_resilience_scores(self, limit: int = 20, service: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"service": service})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.resilience_scores {where} ORDER BY computed_at DESC LIMIT {self._limit(limit)}")

    async def recent_chaos_safety_violations(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.chaos_safety_violations ORDER BY created_at DESC LIMIT {self._limit(limit)}")

    async def recent_chaos_campaigns(self, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"status": status})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.chaos_campaigns {where} ORDER BY updated_at DESC LIMIT {self._limit(limit)}")

    async def chaos_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        safe = self._quote(campaign_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.chaos_campaigns WHERE campaign_id = {safe} ORDER BY updated_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def recent_chaos_campaign_runs(self, limit: int = 20, campaign_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"campaign_id": campaign_id, "status": status})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.chaos_campaign_runs {where} ORDER BY started_at DESC LIMIT {self._limit(limit)}")

    async def chaos_campaign_run(self, run_id: str) -> dict[str, Any] | None:
        safe = self._quote(run_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.chaos_campaign_runs WHERE run_id = {safe} ORDER BY started_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def chaos_campaign_steps(self, run_id: str) -> list[dict[str, Any]]:
        safe = self._quote(run_id)
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.chaos_campaign_steps WHERE run_id = {safe} ORDER BY sequence ASC, created_at ASC LIMIT 200")

    async def chaos_stats(self) -> dict[str, int | None]:
        stats: dict[str, int | None] = {}
        for table in ["chaos_experiment_plans", "chaos_experiment_runs", "chaos_observations", "resilience_scores", "chaos_safety_violations", "chaos_policy_audit", "chaos_campaigns", "chaos_campaign_runs", "chaos_campaign_steps"]:
            try:
                stats[table] = await self.count(table)
            except Exception:
                stats[table] = None
        return stats

    async def insert_remediation_plan(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("remediation_plans", [row])

    async def recent_remediation_plans(self, limit: int = 20, service: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"service": service, "status": status})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.remediation_plans {where} ORDER BY created_at DESC LIMIT {self._limit(limit)}")

    async def remediation_plan(self, plan_id: str) -> dict[str, Any] | None:
        safe = self._quote(plan_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.remediation_plans WHERE plan_id = {safe} ORDER BY updated_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def insert_remediation_approval(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("remediation_approvals", [row])

    async def recent_remediation_approvals(self, limit: int = 20, plan_id: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"plan_id": plan_id})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.remediation_approvals {where} ORDER BY decided_at DESC LIMIT {self._limit(limit)}")

    async def remediation_approval(self, approval_id: str) -> dict[str, Any] | None:
        safe = self._quote(approval_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.remediation_approvals WHERE approval_id = {safe} ORDER BY decided_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def latest_remediation_approval(self, plan_id: str) -> dict[str, Any] | None:
        safe = self._quote(plan_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.remediation_approvals WHERE plan_id = {safe} ORDER BY decided_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def insert_remediation_execution(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("remediation_executions", [row])

    async def recent_remediation_executions(self, limit: int = 20, plan_id: str | None = None, status: str | None = None, service: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"plan_id": plan_id, "status": status, "service": service})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.remediation_executions {where} ORDER BY started_at DESC LIMIT {self._limit(limit)}")

    async def remediation_execution(self, execution_id: str) -> dict[str, Any] | None:
        safe = self._quote(execution_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.remediation_executions WHERE execution_id = {safe} ORDER BY started_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def latest_remediation_dry_run(self, plan_id: str) -> dict[str, Any] | None:
        safe = self._quote(plan_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.remediation_executions WHERE plan_id = {safe} AND dry_run = 1 AND status = 'completed' AND validation_status IN ('passed', 'degraded') ORDER BY started_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def insert_remediation_rollback_plan(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("remediation_rollback_plans", [row])

    async def recent_remediation_rollback_plans(self, limit: int = 20, execution_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"execution_id": execution_id, "status": status})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.remediation_rollback_plans {where} ORDER BY created_at DESC LIMIT {self._limit(limit)}")

    async def remediation_rollback_plan(self, rollback_plan_id: str) -> dict[str, Any] | None:
        safe = self._quote(rollback_plan_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.remediation_rollback_plans WHERE rollback_plan_id = {safe} ORDER BY updated_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def insert_remediation_verification_result(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("remediation_verification_results", [row])

    async def recent_remediation_verification_results(self, limit: int = 20, execution_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"execution_id": execution_id, "status": status})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.remediation_verification_results {where} ORDER BY completed_at DESC LIMIT {self._limit(limit)}")

    async def remediation_verification_result(self, verification_id: str) -> dict[str, Any] | None:
        safe = self._quote(verification_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.remediation_verification_results WHERE verification_id = {safe} ORDER BY completed_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def remediation_verification_for_execution(self, execution_id: str) -> dict[str, Any] | None:
        safe = self._quote(execution_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.remediation_verification_results WHERE execution_id = {safe} ORDER BY completed_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def insert_remediation_safety_violation(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("remediation_safety_violations", [row])

    async def insert_remediation_policy_audit(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("remediation_policy_audit", [row])

    async def remediation_stats(self) -> dict[str, int | None]:
        stats: dict[str, int | None] = {}
        for table in ["remediation_plans", "remediation_approvals", "remediation_executions", "remediation_rollback_plans", "remediation_verification_results", "remediation_safety_violations", "remediation_policy_audit"]:
            try:
                stats[table] = await self.count(table)
            except Exception:
                stats[table] = None
        return stats

    async def insert_autopilot_run(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("autopilot_runs", [row])

    async def insert_autopilot_step(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("autopilot_steps", [row])

    async def recent_autopilot_runs(self, limit: int = 20, service: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        where = self._where({"service": service, "status": status})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.autopilot_runs {where} ORDER BY created_at DESC LIMIT {self._limit(limit)}")

    async def autopilot_run(self, run_id: str) -> dict[str, Any] | None:
        safe = self._quote(run_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.autopilot_runs WHERE run_id = {safe} ORDER BY updated_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def autopilot_steps(self, run_id: str) -> list[dict[str, Any]]:
        safe = self._quote(run_id)
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.autopilot_steps WHERE run_id = {safe} ORDER BY created_at ASC LIMIT 200")

    async def insert_scheduler_item(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("scheduler_items", [row])

    async def scheduler_items(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.scheduler_items ORDER BY updated_at DESC LIMIT {self._limit(limit * 5)}")
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            item_id = str(row.get("item_id") or "")
            if item_id and item_id not in latest:
                latest[item_id] = row
        return list(latest.values())[: self._limit(limit)]

    async def scheduler_item(self, item_id: str) -> dict[str, Any] | None:
        safe = self._quote(item_id)
        rows = await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.scheduler_items WHERE item_id = {safe} ORDER BY updated_at DESC LIMIT 1")
        return rows[0] if rows else None

    async def insert_scheduler_decision(self, row: dict[str, Any]) -> int:
        return await self.insert_rows("scheduler_decisions", [row])

    async def scheduler_decisions(
        self,
        limit: int = 100,
        item_id: str | None = None,
        status: str | None = None,
        idempotency_key: str | None = None,
    ) -> list[dict[str, Any]]:
        where = self._where({"item_id": item_id, "status": status, "idempotency_key": idempotency_key})
        return await self.fetch_json_rows(f"SELECT * FROM {self.settings.clickhouse_database}.scheduler_decisions {where} ORDER BY evaluated_at DESC LIMIT {self._limit(limit)}")

    async def scheduler_run_count_since(self, item_id: str, since: str) -> int:
        safe_item = self._quote(item_id)
        safe_since = self._quote(since)
        text = await self.fetch_text(f"SELECT count() FROM {self.settings.clickhouse_database}.scheduler_decisions WHERE item_id = {safe_item} AND status = 'run_started' AND evaluated_at >= parseDateTime64BestEffort({safe_since})")
        return int(text.strip() or "0")

    @staticmethod
    def json_dumps(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)

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

    def _audit_where(self, filters: dict[str, str | None], start_time: str | None = None, end_time: str | None = None) -> str:
        clauses = [f"{key} = {self._quote(value)}" for key, value in filters.items() if value]
        if start_time:
            clauses.append(f"timestamp >= parseDateTime64BestEffort({self._quote(start_time)})")
        if end_time:
            clauses.append(f"timestamp <= parseDateTime64BestEffort({self._quote(end_time)})")
        return "WHERE " + " AND ".join(clauses) if clauses else ""

    def _latest_chaos_runs_query(self, filters: dict[str, str | None] | None = None) -> str:
        db = self.settings.clickhouse_database
        clauses = ["rn = 1"]
        if filters:
            clauses.extend(f"{key} = {self._quote(value)}" for key, value in filters.items() if value)
        where = " AND ".join(clauses)
        return f"""
SELECT
    run_id,
    plan_id,
    experiment_id,
    started_at,
    completed_at,
    status,
    dry_run,
    approved,
    experiment_kind,
    target_namespace,
    target_service,
    target_workload,
    chaos_resource_name,
    chaos_resource_uid,
    duration_seconds,
    cleanup_status,
    error_message,
    run_json,
    latest_state_at
FROM (
    SELECT
        *,
        ifNull(completed_at, started_at) AS latest_state_at,
        row_number() OVER (
            PARTITION BY run_id
            ORDER BY
                ifNull(completed_at, started_at) DESC,
                multiIf(status = 'completed', 5, status = 'failed', 4, status = 'dry_run', 3, status = 'running', 2, 1) DESC
        ) AS rn
    FROM {db}.chaos_experiment_runs
)
WHERE {where}
"""


def schema_statements(database: str = "cascade") -> list[str]:
    db = database
    return [
        f"CREATE DATABASE IF NOT EXISTS {db}",
        f"""
CREATE TABLE IF NOT EXISTS {db}.audit_events (
    event_id String,
    timestamp DateTime64(3),
    event_type String,
    subsystem String,
    severity String,
    run_id String,
    correlation_id String,
    service String,
    namespace String,
    actor String,
    action String,
    decision String,
    status String,
    risk_level String,
    policy_decision_id String,
    remediation_execution_id String,
    verification_id String,
    rollback_plan_id String,
    autopilot_run_id String,
    chaos_experiment_id String,
    campaign_id String,
    rca_report_id String,
    topology_node_or_edge_id String,
    evidence_summary String,
    raw_payload_json String,
    user_safe_message String
) ENGINE = ReplacingMergeTree(timestamp)
ORDER BY (timestamp, subsystem, service, event_id)
""",
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
    latency_p50_ms Float64,
    latency_p95_ms Float64,
    latency_p99_ms Float64,
    request_rate Float64,
    error_rate Float64,
    restart_rate Float64,
    unhealthy_rate Float64,
    readiness_rate Float64,
    availability_rate Float64,
    warning_event_count Float64,
    missing_metric_count UInt64,
    dependency_unhealthy_count UInt64,
    feature_vector_json String,
    source_query_hash String
) ENGINE = MergeTree
ORDER BY (service, window_start, window_id)
""",
        f"ALTER TABLE {db}.telemetry_feature_windows ADD COLUMN IF NOT EXISTS latency_p50_ms Float64 AFTER max_latency_ms",
        f"ALTER TABLE {db}.telemetry_feature_windows ADD COLUMN IF NOT EXISTS latency_p95_ms Float64 AFTER latency_p50_ms",
        f"ALTER TABLE {db}.telemetry_feature_windows ADD COLUMN IF NOT EXISTS latency_p99_ms Float64 AFTER latency_p95_ms",
        f"ALTER TABLE {db}.telemetry_feature_windows ADD COLUMN IF NOT EXISTS request_rate Float64 AFTER latency_p99_ms",
        f"ALTER TABLE {db}.telemetry_feature_windows ADD COLUMN IF NOT EXISTS readiness_rate Float64 AFTER unhealthy_rate",
        f"ALTER TABLE {db}.telemetry_feature_windows ADD COLUMN IF NOT EXISTS availability_rate Float64 AFTER readiness_rate",
        f"ALTER TABLE {db}.telemetry_feature_windows ADD COLUMN IF NOT EXISTS warning_event_count Float64 AFTER availability_rate",
        f"ALTER TABLE {db}.telemetry_feature_windows ADD COLUMN IF NOT EXISTS missing_metric_count UInt64 AFTER warning_event_count",
        f"ALTER TABLE {db}.telemetry_feature_windows ADD COLUMN IF NOT EXISTS dependency_unhealthy_count UInt64 AFTER missing_metric_count",
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
) ENGINE = ReplacingMergeTree(detected_at)
ORDER BY (anomaly_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.causal_reports (
    report_id String,
    generated_at DateTime64(3),
    target_service String,
    target_feature String,
    source_feature String,
    status String,
    summary String,
    window_start Nullable(DateTime64(3)),
    window_end Nullable(DateTime64(3)),
    candidate_count UInt64,
    methodology_json String,
    limitations_json String,
    report_json String
) ENGINE = ReplacingMergeTree(generated_at)
ORDER BY (generated_at, report_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.causal_candidates (
    report_id String,
    candidate_id String,
    generated_at DateTime64(3),
    rank UInt64,
    source_service String,
    target_service String,
    source_feature String,
    target_feature String,
    status String,
    rank_score Float64,
    best_p_value Nullable(Float64),
    effect_size Float64,
    lag_windows UInt64,
    sample_count UInt64,
    pearson_json String,
    spearman_json String,
    granger_json String,
    topology_distance Nullable(Int64),
    anomaly_context_json String,
    limitations_json String,
    candidate_json String
) ENGINE = ReplacingMergeTree(generated_at)
ORDER BY (report_id, rank, candidate_id)
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
        f"""
CREATE TABLE IF NOT EXISTS {db}.rca_reports (
    report_id String,
    generated_at DateTime64(3),
    status String,
    target_service String,
    likely_root_cause_service String,
    confidence_score Float64,
    affected_services_json String,
    related_chaos_json String,
    evidence_json String,
    timeline_json String,
    limitations_json String,
    explanation String,
    report_json String
) ENGINE = ReplacingMergeTree(generated_at)
ORDER BY (generated_at, report_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.knowledge_documents (
    document_id String,
    source_type String,
    document_type String,
    title String,
    source_path String,
    source_uri String,
    content_hash String,
    ingested_at DateTime64(3),
    updated_at DateTime64(3),
    phase String,
    service String,
    namespace String,
    severity String,
    tags_json String,
    metadata_json String,
    raw_content String
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (source_type, document_type, document_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.knowledge_chunks (
    chunk_id String,
    document_id String,
    chunk_index UInt64,
    source_type String,
    document_type String,
    title String,
    source_path String,
    content_hash String,
    chunk_hash String,
    ingested_at DateTime64(3),
    phase String,
    service String,
    namespace String,
    severity String,
    tags_json String,
    metadata_json String,
    chunk_text String,
    embedding_model String,
    qdrant_collection String,
    qdrant_point_id String
) ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (source_type, document_type, document_id, chunk_index, chunk_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.knowledge_ingestion_runs (
    run_id String,
    started_at DateTime64(3),
    completed_at DateTime64(3),
    source String,
    source_type String,
    documents_seen UInt64,
    documents_ingested UInt64,
    chunks_created UInt64,
    chunks_indexed UInt64,
    status String,
    config_json String,
    error_message String
) ENGINE = MergeTree
ORDER BY (started_at, run_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.knowledge_queries (
    query_id String,
    queried_at DateTime64(3),
    query_text String,
    filters_json String,
    result_count UInt64,
    top_score Float64,
    latency_ms Float64,
    response_json String
) ENGINE = MergeTree
ORDER BY (queried_at, query_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.investigation_runs (
    investigation_id String,
    created_at DateTime64(3),
    updated_at DateTime64(3),
    completed_at Nullable(DateTime64(3)),
    status String,
    mode String,
    trigger_type String,
    trigger_id String,
    service String,
    namespace String,
    severity String,
    risk_score Float64,
    title String,
    objective String,
    final_summary String,
    confidence Float64,
    tools_used_json String,
    evidence_refs_json String,
    config_json String,
    error_message String
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (created_at, investigation_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.agent_steps (
    step_id String,
    investigation_id String,
    created_at DateTime64(3),
    node_name String,
    agent_role String,
    step_type String,
    status String,
    input_json String,
    output_json String,
    tool_name String,
    tool_latency_ms Float64,
    error_message String
) ENGINE = MergeTree
ORDER BY (investigation_id, created_at, step_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.investigation_reports (
    report_id String,
    investigation_id String,
    generated_at DateTime64(3),
    title String,
    summary String,
    suspected_root_cause String,
    affected_services_json String,
    evidence_json String,
    timeline_json String,
    anomaly_refs_json String,
    knowledge_refs_json String,
    recommended_next_steps_json String,
    suggested_remediation_json String,
    confidence Float64,
    markdown_report String,
    report_json String
) ENGINE = ReplacingMergeTree(generated_at)
ORDER BY (investigation_id, generated_at, report_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.agent_tool_calls (
    call_id String,
    investigation_id String,
    called_at DateTime64(3),
    tool_name String,
    target_service String,
    status String,
    latency_ms Float64,
    request_json String,
    response_summary String,
    error_message String
) ENGINE = MergeTree
ORDER BY (investigation_id, called_at, call_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.chaos_experiment_plans (
    plan_id String,
    created_at DateTime64(3),
    updated_at DateTime64(3),
    status String,
    plan_type String,
    experiment_kind String,
    target_namespace String,
    target_service String,
    target_workload String,
    target_selector_json String,
    duration_seconds UInt64,
    blast_radius_score Float64,
    safety_score Float64,
    risk_level String,
    objective String,
    hypothesis String,
    expected_impact String,
    safety_policy_json String,
    manifest_json String,
    plan_json String
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (created_at, plan_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.chaos_experiment_runs (
    run_id String,
    plan_id String,
    experiment_id String,
    started_at DateTime64(3),
    completed_at Nullable(DateTime64(3)),
    status String,
    dry_run UInt8,
    approved UInt8,
    experiment_kind String,
    target_namespace String,
    target_service String,
    target_workload String,
    chaos_resource_name String,
    chaos_resource_uid String,
    duration_seconds UInt64,
    cleanup_status String,
    error_message String,
    run_json String
) ENGINE = ReplacingMergeTree(started_at)
ORDER BY (started_at, run_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.chaos_observations (
    observation_id String,
    run_id String,
    plan_id String,
    observed_at DateTime64(3),
    observation_window_seconds UInt64,
    telemetry_events_count UInt64,
    anomaly_events_count UInt64,
    incidents_count UInt64,
    investigation_id String,
    affected_services_json String,
    telemetry_summary_json String,
    anomaly_summary_json String,
    incident_summary_json String,
    observation_json String
) ENGINE = MergeTree
ORDER BY (run_id, observed_at, observation_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.resilience_scores (
    score_id String,
    run_id String,
    plan_id String,
    computed_at DateTime64(3),
    service String,
    namespace String,
    experiment_kind String,
    resilience_score Float64,
    recovery_score Float64,
    blast_radius_score Float64,
    anomaly_penalty Float64,
    incident_penalty Float64,
    evidence_score Float64,
    grade String,
    explanation String,
    recommendations_json String,
    score_json String
) ENGINE = ReplacingMergeTree(computed_at)
ORDER BY (service, computed_at, score_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.chaos_safety_violations (
    violation_id String,
    created_at DateTime64(3),
    plan_id String,
    run_id String,
    violation_type String,
    severity String,
    message String,
    policy_json String,
    request_json String
) ENGINE = MergeTree
ORDER BY (created_at, violation_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.chaos_policy_audit (
    audit_id String,
    checked_at DateTime64(3),
    plan_id String,
    experiment_kind String,
    namespace String,
    service String,
    allowed UInt8,
    risk_level String,
    findings_json String,
    policy_json String
) ENGINE = MergeTree
ORDER BY (checked_at, audit_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.chaos_campaigns (
    campaign_id String,
    created_at DateTime64(3),
    updated_at DateTime64(3),
    status String,
    name String,
    target_namespace String,
    allowed_services_json String,
    experiment_templates_json String,
    schedule_json String,
    max_experiments_per_run UInt64,
    blast_radius_limit Float64,
    cooldown_seconds UInt64,
    dry_run UInt8,
    local_demo_execution_enabled UInt8,
    stop_conditions_json String,
    campaign_json String
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (updated_at, campaign_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.chaos_campaign_runs (
    run_id String,
    campaign_id String,
    started_at DateTime64(3),
    completed_at Nullable(DateTime64(3)),
    status String,
    dry_run UInt8,
    requested_by String,
    experiments_attempted UInt64,
    experiments_succeeded UInt64,
    experiments_blocked UInt64,
    experiments_failed UInt64,
    services_json String,
    report_json String,
    error_message String,
    run_json String
) ENGINE = ReplacingMergeTree(started_at)
ORDER BY (started_at, run_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.chaos_campaign_steps (
    step_id String,
    run_id String,
    campaign_id String,
    created_at DateTime64(3),
    sequence UInt64,
    status String,
    plan_id String,
    chaos_run_id String,
    experiment_kind String,
    target_service String,
    blocked_reason String,
    evidence_before_json String,
    evidence_after_json String,
    result_json String,
    cleanup_status String,
    step_json String
) ENGINE = MergeTree
ORDER BY (run_id, sequence, created_at, step_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.remediation_plans (
    plan_id String,
    created_at DateTime64(3),
    updated_at DateTime64(3),
    status String,
    trigger_type String,
    trigger_id String,
    source_investigation_id String,
    source_anomaly_id String,
    source_incident_id String,
    source_chaos_run_id String,
    service String,
    namespace String,
    severity String,
    risk_score Float64,
    confidence Float64,
    action_type String,
    action_summary String,
    remediation_steps_json String,
    rollback_steps_json String,
    evidence_refs_json String,
    safety_findings_json String,
    dry_run_manifest_json String,
    plan_json String
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (created_at, plan_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.remediation_approvals (
    approval_id String,
    plan_id String,
    decided_at DateTime64(3),
    decision String,
    approver String,
    approver_role String,
    reason String,
    expires_at Nullable(DateTime64(3)),
    approval_metadata_json String
) ENGINE = MergeTree
ORDER BY (plan_id, decided_at, approval_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.remediation_executions (
    execution_id String,
    plan_id String,
    approval_id String,
    started_at DateTime64(3),
    completed_at Nullable(DateTime64(3)),
    status String,
    dry_run UInt8,
    executed UInt8,
    action_type String,
    namespace String,
    service String,
    resource_kind String,
    resource_name String,
    validation_status String,
    execution_status String,
    rollback_available UInt8,
    output_summary String,
    error_message String,
    execution_json String
) ENGINE = ReplacingMergeTree(started_at)
ORDER BY (started_at, execution_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.remediation_rollback_plans (
    rollback_plan_id String,
    execution_id String,
    plan_id String,
    created_at DateTime64(3),
    updated_at DateTime64(3),
    action_type String,
    namespace String,
    service String,
    rollback_type String,
    available UInt8,
    auto_executable UInt8,
    status String,
    reason String,
    snapshot_json String,
    actions_json String,
    result_json String,
    rollback_plan_json String
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (created_at, rollback_plan_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.remediation_verification_results (
    verification_id String,
    execution_id String,
    plan_id String,
    rollback_plan_id String,
    created_at DateTime64(3),
    completed_at DateTime64(3),
    action_type String,
    namespace String,
    service String,
    status String,
    evidence_quality String,
    rollback_status String,
    summary String,
    before_json String,
    after_json String,
    comparisons_json String,
    limitations_json String,
    rollback_json String,
    verification_json String
) ENGINE = ReplacingMergeTree(completed_at)
ORDER BY (completed_at, verification_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.remediation_safety_violations (
    violation_id String,
    created_at DateTime64(3),
    plan_id String,
    execution_id String,
    violation_type String,
    severity String,
    message String,
    policy_json String,
    request_json String
) ENGINE = MergeTree
ORDER BY (created_at, violation_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.remediation_policy_audit (
    audit_id String,
    checked_at DateTime64(3),
    plan_id String,
    action_type String,
    namespace String,
    service String,
    allowed UInt8,
    risk_level String,
    findings_json String,
    policy_json String
) ENGINE = MergeTree
ORDER BY (checked_at, audit_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.autopilot_runs (
    run_id String,
    created_at DateTime64(3),
    updated_at DateTime64(3),
    completed_at Nullable(DateTime64(3)),
    status String,
    final_result String,
    mode String,
    trigger_type String,
    trigger_id String,
    service String,
    namespace String,
    objective String,
    anomaly_id String,
    investigation_id String,
    remediation_plan_id String,
    approval_id String,
    dry_run_execution_id String,
    execution_id String,
    proposed_action String,
    error_message String,
    evidence_json String,
    recommendation_json String,
    action_json String,
    verification_json String,
    run_json String
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (created_at, run_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.autopilot_steps (
    step_id String,
    run_id String,
    created_at DateTime64(3),
    state String,
    status String,
    summary String,
    input_json String,
    output_json String,
    error_message String,
    step_json String
) ENGINE = MergeTree
ORDER BY (run_id, created_at, step_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.scheduler_items (
    item_id String,
    item_type String,
    target_id String,
    name String,
    schedule_json String,
    enabled UInt8,
    paused UInt8,
    mode String,
    next_run_at Nullable(DateTime64(3)),
    last_run_at Nullable(DateTime64(3)),
    cooldown_seconds UInt64,
    max_runs_per_window UInt64,
    window_seconds UInt64,
    failure_count UInt64,
    status String,
    payload_json String,
    updated_at DateTime64(3)
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (item_id)
""",
        f"""
CREATE TABLE IF NOT EXISTS {db}.scheduler_decisions (
    decision_id String,
    item_id String,
    item_type String,
    target_id String,
    evaluated_at DateTime64(3),
    due_at Nullable(DateTime64(3)),
    status String,
    action String,
    reason String,
    idempotency_key String,
    run_id String,
    dry_run UInt8,
    skipped_missed_windows UInt64,
    payload_json String,
    error_message String
) ENGINE = MergeTree
ORDER BY (item_id, evaluated_at, decision_id)
""",
        f"ALTER TABLE {db}.telemetry_events MODIFY TTL toDateTime(observed_at) + INTERVAL 14 DAY DELETE",
        f"ALTER TABLE {db}.telemetry_feature_windows MODIFY TTL toDateTime(window_end) + INTERVAL 45 DAY DELETE",
        f"ALTER TABLE {db}.anomaly_events MODIFY TTL toDateTime(detected_at) + INTERVAL 90 DAY DELETE",
        f"ALTER TABLE {db}.experiment_events MODIFY TTL toDateTime(observed_at) + INTERVAL 90 DAY DELETE",
        f"ALTER TABLE {db}.model_runs MODIFY TTL toDateTime(completed_at) + INTERVAL 90 DAY DELETE",
    ]
