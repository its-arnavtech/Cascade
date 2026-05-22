from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str, separators=(",", ":"), sort_keys=True)


def parse_datetime(value: Any, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return fallback or datetime.now(UTC)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def compact_hash(prefix: str, payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}-{digest}"


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def service_from_event(event: dict[str, Any]) -> str:
    return str(
        event.get("service")
        or event.get("service_name")
        or event.get("target_service")
        or event.get("root_cause_service")
        or event.get("workload")
        or event.get("pod_name")
        or "unknown"
    )


def namespace_from_event(event: dict[str, Any]) -> str:
    return str(event.get("namespace") or event.get("target_namespace") or "unknown")


def map_telemetry_event(event: dict[str, Any], source_topic: str = "telemetry.enriched") -> dict[str, Any]:
    observed = parse_datetime(event.get("timestamp") or event.get("observed_at"))
    ingested = parse_datetime(event.get("ingestion_timestamp") or event.get("ingested_at"))
    normalized = as_dict(event.get("normalized_fields"))
    labels = as_dict(event.get("labels"))
    event_id = str(event.get("event_id") or compact_hash("telemetry", event))
    service = service_from_event(event)
    return {
        "event_id": event_id,
        "observed_at": isoformat(observed),
        "ingested_at": isoformat(ingested),
        "source_topic": source_topic,
        "event_type": str(event.get("event_type") or "telemetry_event"),
        "namespace": namespace_from_event(event),
        "service": service,
        "workload": str(event.get("workload") or event.get("service_name") or service),
        "pod": str(event.get("pod") or event.get("pod_name") or ""),
        "severity": severity_from_event(event),
        "health_status": str(event.get("health_status") or event.get("derived_status") or event.get("pod_phase") or "unknown"),
        "experiment_id": str(event.get("experiment_id") or ""),
        "trace_id": str(event.get("trace_id") or ""),
        "raw_json": stable_json(event),
        "enriched_json": stable_json(event),
        "labels_json": stable_json(labels),
        "numeric_features_json": stable_json(normalized),
    }


def map_experiment_event(event: dict[str, Any], source_topic: str = "experiments.events") -> dict[str, Any]:
    started = parse_datetime(event.get("started_at") or event.get("observed_at"))
    completed_value = event.get("completed_at")
    completed = parse_datetime(completed_value) if completed_value else None
    observed = parse_datetime(event.get("observed_at") or event.get("timestamp") or completed_value or event.get("started_at"))
    experiment_id = str(event.get("experiment_id") or compact_hash("experiment", event))
    return {
        "event_id": str(event.get("event_id") or compact_hash("experiment-event", event)),
        "experiment_id": experiment_id,
        "experiment_type": str(event.get("experiment_type") or event.get("type") or "unknown"),
        "target_namespace": namespace_from_event(event),
        "target_service": str(event.get("target_service") or service_from_event(event)),
        "target_workload": str(event.get("target_workload") or event.get("workload") or event.get("target_service") or ""),
        "status": str(event.get("status") or "unknown"),
        "started_at": isoformat(started),
        "completed_at": isoformat(completed) if completed else None,
        "observed_at": isoformat(observed),
        "ingested_at": isoformat(datetime.now(UTC)),
        "source_topic": source_topic,
        "event_json": stable_json(event),
    }


def map_incident(event: dict[str, Any]) -> dict[str, Any]:
    incident_id = str(event.get("incident_id") or compact_hash("incident", event))
    started = parse_datetime(event.get("started_at") or event.get("first_seen_at"))
    generated = parse_datetime(event.get("generated_at") or event.get("created_at"))
    confidence = event.get("confidence", 0.0)
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0
    return {
        "incident_id": incident_id,
        "experiment_id": str(event.get("experiment_id") or ""),
        "root_cause_service": str(event.get("root_cause_service") or "unknown"),
        "root_cause_summary": str(event.get("root_cause_summary") or event.get("summary") or ""),
        "severity": severity_from_event(event),
        "status": str(event.get("status") or "reconstructed"),
        "confidence": confidence_value,
        "first_seen_at": isoformat(started),
        "last_seen_at": isoformat(parse_datetime(event.get("last_seen_at") or event.get("generated_at"), generated)),
        "created_at": isoformat(generated),
        "affected_services_json": stable_json(as_list(event.get("affected_services"))),
        "causal_chain_json": stable_json(as_list(event.get("causal_chain"))),
        "evidence_json": stable_json(as_list(event.get("evidence"))),
        "incident_json": stable_json(event),
    }


def map_incident_report(report: dict[str, Any], incident: dict[str, Any] | None = None) -> dict[str, Any]:
    incident = incident or {}
    merged = {**incident, **report}
    generated = parse_datetime(report.get("generated_at") or incident.get("generated_at"))
    incident_id = str(merged.get("incident_id") or compact_hash("incident", incident or report))
    return {
        "report_id": str(report.get("report_id") or compact_hash("report", merged)),
        "incident_id": incident_id,
        "experiment_id": str(merged.get("experiment_id") or ""),
        "generated_at": isoformat(generated),
        "root_cause_service": str(merged.get("root_cause_service") or report.get("root_cause") or "unknown"),
        "severity": severity_from_event(merged),
        "markdown_report": str(report.get("markdown") or report.get("markdown_report") or ""),
        "report_json": stable_json(merged),
    }


def map_topology_snapshot(topology: dict[str, Any]) -> dict[str, Any]:
    dependencies = topology.get("dependencies") or topology.get("topology") or {}
    edges = topology.get("edges") if isinstance(topology.get("edges"), list) else []
    nodes = topology.get("nodes") if isinstance(topology.get("nodes"), list) else []
    edge_count = sum(len(v) for v in dependencies.values()) if isinstance(dependencies, dict) else len(edges)
    return {
        "snapshot_id": str(topology.get("snapshot_id") or compact_hash("topology", topology)),
        "captured_at": isoformat(parse_datetime(topology.get("captured_at"))),
        "topology_json": stable_json(topology),
        "service_count": len(dependencies) if isinstance(dependencies, dict) else len(nodes),
        "edge_count": edge_count,
    }


def severity_from_event(event: dict[str, Any]) -> str:
    severity = event.get("severity")
    if severity:
        return str(severity)
    status = str(event.get("derived_status") or event.get("health_status") or event.get("status") or "").lower()
    if status in {"failed", "degraded"}:
        return "warning"
    if status in {"cancelled"}:
        return "info"
    flags = as_list(event.get("anomaly_flags"))
    return "warning" if flags else "info"


def build_memory_document(memory_type: str, payload: dict[str, Any]) -> str:
    service = service_from_event(payload)
    namespace = namespace_from_event(payload)
    parts = [
        f"memory type {memory_type}",
        f"service {service}",
        f"namespace {namespace}",
        f"workload {payload.get('workload') or payload.get('target_workload') or payload.get('pod_name') or ''}",
        f"experiment {payload.get('experiment_id') or ''}",
        f"incident {payload.get('incident_id') or ''}",
        f"root cause {payload.get('root_cause_service') or payload.get('root_cause') or ''}",
        f"health {payload.get('health_status') or payload.get('derived_status') or payload.get('status') or ''}",
        f"event type {payload.get('event_type') or payload.get('experiment_type') or ''}",
        f"severity {severity_from_event(payload)}",
        f"affected services {' '.join(str(x) for x in as_list(payload.get('affected_services')))}",
        f"causal chain {' -> '.join(str(x) for x in as_list(payload.get('causal_chain')))}",
        f"summary {payload.get('summary') or payload.get('root_cause_summary') or payload.get('markdown') or ''}",
    ]
    normalized = as_dict(payload.get("normalized_fields"))
    if normalized:
        parts.append(f"metrics {stable_json(normalized)}")
    labels = as_dict(payload.get("labels"))
    if labels:
        parts.append(f"labels {stable_json(labels)}")
    return " | ".join(part.strip() for part in parts if part.strip())


def build_memory_payload(memory_type: str, payload: dict[str, Any], source: str, source_topic: str = "") -> dict[str, Any]:
    summary = build_memory_document(memory_type, payload)
    return {
        "memory_id": str(payload.get("memory_id") or compact_hash(f"memory-{memory_type}", payload)),
        "memory_type": memory_type,
        "event_id": str(payload.get("event_id") or ""),
        "incident_id": str(payload.get("incident_id") or ""),
        "experiment_id": str(payload.get("experiment_id") or ""),
        "service": service_from_event(payload),
        "namespace": namespace_from_event(payload),
        "workload": str(payload.get("workload") or payload.get("target_workload") or payload.get("pod_name") or ""),
        "severity": severity_from_event(payload),
        "health_status": str(payload.get("health_status") or payload.get("derived_status") or payload.get("status") or ""),
        "event_type": str(payload.get("event_type") or payload.get("experiment_type") or memory_type),
        "root_cause_service": str(payload.get("root_cause_service") or payload.get("root_cause") or ""),
        "observed_at": str(payload.get("observed_at") or payload.get("timestamp") or payload.get("started_at") or ""),
        "generated_at": str(payload.get("generated_at") or ""),
        "summary": summary[:2000],
        "source": source,
        "source_topic": source_topic,
        "tags": [memory_type, service_from_event(payload), namespace_from_event(payload)],
        "compact_json": stable_json(payload)[:8000],
    }
