from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from services.shared.events.mapping import parse_datetime, stable_json
from services.shared.features.schema import FEATURE_KEYS
from services.shared.features.windows import floor_to_window, window_end


def ch_datetime(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def stable_window_id(service: str, namespace: str, workload: str, start: datetime, end: datetime) -> str:
    key = f"{service}|{namespace}|{workload}|{ch_datetime(start)}|{ch_datetime(end)}"
    return "window-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def source_query_hash(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def telemetry_query(database: str, lookback_minutes: int, service: str | None = None, namespace: str | None = None) -> str:
    clauses = [f"observed_at >= now64(3) - INTERVAL {max(1, int(lookback_minutes))} MINUTE"]
    if service:
        clauses.append(f"service = '{service.replace("'", "\\'")}'")
    if namespace:
        clauses.append(f"namespace = '{namespace.replace("'", "\\'")}'")
    where = " AND ".join(clauses)
    return f"SELECT * FROM {database}.telemetry_events WHERE {where} ORDER BY observed_at ASC"


def extract_feature_windows(events: list[dict[str, Any]], window_seconds: int = 300, extracted_at: datetime | None = None) -> list[dict[str, Any]]:
    extracted = extracted_at or datetime.now(UTC)
    grouped: dict[tuple[str, str, str, datetime], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        observed = parse_datetime(event.get("observed_at") or event.get("timestamp"))
        service = str(event.get("service") or event.get("service_name") or "unknown")
        namespace = str(event.get("namespace") or "unknown")
        workload = str(event.get("workload") or event.get("pod") or event.get("pod_name") or service)
        grouped[(service, namespace, workload, floor_to_window(observed, window_seconds))].append(event)

    rows = []
    for (service, namespace, workload, start), group in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][3])):
        end = window_end(start, window_seconds)
        vector = build_feature_vector(group)
        row = {
            "window_id": stable_window_id(service, namespace, workload, start, end),
            "service": service,
            "namespace": namespace,
            "workload": workload,
            "window_start": ch_datetime(start),
            "window_end": ch_datetime(end),
            "extracted_at": ch_datetime(extracted),
            "source_query_hash": source_query_hash(service, namespace, workload, ch_datetime(start), len(group)),
            **vector,
            "feature_vector_json": stable_json(vector),
        }
        rows.append(row)
    return rows


def build_feature_vector(events: list[dict[str, Any]]) -> dict[str, Any]:
    event_count = len(events)
    healthy = warning = error = unhealthy = restart_signal = 0
    cpus: list[float] = []
    memories: list[float] = []
    latencies: list[float] = []
    latency_p50s: list[float] = []
    latency_p95s: list[float] = []
    latency_p99s: list[float] = []
    request_rates: list[float] = []
    readiness_values: list[float] = []
    availability_values: list[float] = []
    observed_error_rates: list[float] = []
    warning_events = 0.0
    missing_metric_count = 0
    dependency_unhealthy = 0
    experiment_context = set()
    incident_context = 0

    for event in events:
        status = str(event.get("health_status") or event.get("derived_status") or "").lower()
        severity = str(event.get("severity") or "").lower()
        if status in {"healthy", "running", "ok"}:
            healthy += 1
        if status in {"warning", "degraded", "unhealthy", "failed"} or severity in {"warning", "high", "critical", "error"}:
            warning += 1
        if status in {"unhealthy", "failed", "error"} or severity in {"error", "critical"}:
            error += 1
        if status in {"warning", "degraded", "unhealthy", "failed", "error"}:
            unhealthy += 1
        if event.get("experiment_id"):
            experiment_context.add(str(event["experiment_id"]))
        if event.get("incident_id"):
            incident_context += 1

        enriched = _json_obj(event.get("enriched_json") or event.get("raw_json"))
        numeric = _json_obj(event.get("numeric_features_json"))
        cpus.append(_float(numeric.get("cpu_percent"), _float(enriched.get("cpu"), 0.0) * 100.0))
        memories.append(_float(numeric.get("memory_mib"), _float(enriched.get("memory"), 0.0) / (1024 * 1024)))
        latencies.append(_float(numeric.get("latency_ms") or enriched.get("latency_ms"), 0.0))
        latency_p50s.append(_float(numeric.get("latency_p50_ms") or enriched.get("latency_p50_ms"), 0.0))
        latency_p95s.append(_float(numeric.get("latency_p95_ms") or enriched.get("latency_p95_ms"), 0.0))
        latency_p99s.append(_float(numeric.get("latency_p99_ms") or enriched.get("latency_p99_ms"), 0.0))
        request_rates.append(_float(numeric.get("request_rate") or enriched.get("request_rate"), 0.0))
        error_rate_value = _float(numeric.get("error_rate") or enriched.get("error_rate"), 0.0)
        observed_error_rates.append(error_rate_value)
        if error_rate_value > 0:
            error += 1
        ready = numeric.get("ready", enriched.get("ready"))
        service_available = numeric.get("service_available", enriched.get("service_available"))
        if ready is not None:
            readiness_values.append(1.0 if bool(ready) else 0.0)
        if service_available is not None:
            availability_values.append(1.0 if bool(service_available) else 0.0)
        warning_events += _float(numeric.get("warning_event_count") or enriched.get("warning_event_count"), 0.0)
        missing_metric_count += len(enriched.get("missing_metrics") or numeric.get("missing_metrics") or [])
        if any(enriched.get(key) is False or numeric.get(key) is False for key in ("redpanda_healthy", "clickhouse_healthy", "qdrant_healthy")):
            dependency_unhealthy += 1
        restart_count = _float(numeric.get("restart_count"), _float(enriched.get("restart_count"), 0.0))
        if restart_count > 0:
            restart_signal += 1

    denominator = max(event_count, 1)
    vector = {
        "event_count": event_count,
        "unhealthy_count": unhealthy,
        "healthy_count": healthy,
        "restart_signal_count": restart_signal,
        "warning_count": warning,
        "error_count": error,
        "experiment_event_count": len(experiment_context),
        "incident_context_count": incident_context,
        "avg_cpu": _avg(cpus),
        "max_cpu": max(cpus) if cpus else 0.0,
        "avg_memory": _avg(memories),
        "max_memory": max(memories) if memories else 0.0,
        "avg_latency_ms": _avg(latencies),
        "max_latency_ms": max(latencies) if latencies else 0.0,
        "latency_p50_ms": _avg(latency_p50s),
        "latency_p95_ms": max(latency_p95s) if latency_p95s else max(latencies) if latencies else 0.0,
        "latency_p99_ms": max(latency_p99s) if latency_p99s else max(latencies) if latencies else 0.0,
        "request_rate": sum(request_rates),
        "error_rate": max(error / denominator, max(observed_error_rates, default=0.0)),
        "restart_rate": restart_signal / denominator,
        "unhealthy_rate": unhealthy / denominator,
        "readiness_rate": _avg(readiness_values) if readiness_values else 0.0,
        "availability_rate": _avg(availability_values) if availability_values else 0.0,
        "warning_event_count": warning_events,
        "missing_metric_count": missing_metric_count,
        "dependency_unhealthy_count": dependency_unhealthy,
    }
    return {key: vector.get(key, 0.0) for key in FEATURE_KEYS}


def synthetic_feature_window(service: str = "phase4-synthetic-service", namespace: str = "cascade-system") -> dict[str, Any]:
    now = floor_to_window(datetime.now(UTC), 300)
    end = window_end(now, 300)
    vector = {
        "event_count": 20,
        "unhealthy_count": 18,
        "healthy_count": 2,
        "restart_signal_count": 15,
        "warning_count": 18,
        "error_count": 12,
        "experiment_event_count": 1,
        "incident_context_count": 0,
        "avg_cpu": 92.0,
        "max_cpu": 99.0,
        "avg_memory": 1024.0,
        "max_memory": 1536.0,
        "avg_latency_ms": 1200.0,
        "max_latency_ms": 2500.0,
        "latency_p50_ms": 800.0,
        "latency_p95_ms": 2000.0,
        "latency_p99_ms": 2500.0,
        "request_rate": 25.0,
        "error_rate": 0.6,
        "restart_rate": 0.75,
        "unhealthy_rate": 0.9,
        "readiness_rate": 0.25,
        "availability_rate": 0.25,
        "warning_event_count": 4.0,
        "missing_metric_count": 0,
        "dependency_unhealthy_count": 0,
    }
    return {
        "window_id": "synthetic-phase4-" + hashlib.sha256(ch_datetime(now).encode("utf-8")).hexdigest()[:16],
        "service": service,
        "namespace": namespace,
        "workload": "synthetic-demo-workload",
        "window_start": ch_datetime(now),
        "window_end": ch_datetime(end),
        "extracted_at": ch_datetime(datetime.now(UTC)),
        "source_query_hash": "synthetic-phase4-demo",
        **vector,
        "feature_vector_json": stable_json({**vector, "synthetic": True, "purpose": "phase4 acceptance/demo anomaly"}),
    }


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
