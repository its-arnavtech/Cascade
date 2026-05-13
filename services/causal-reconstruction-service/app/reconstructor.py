from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.kafka_reader import EventBuffer
from app.models import IncidentRecord, ReconstructRequest


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def reconstruct(request: ReconstructRequest, buffer: EventBuffer) -> IncidentRecord:
    experiment = _find_experiment(request.experiment_id, buffer)
    started_at = parse_timestamp(experiment.get("started_at")) if experiment else None
    started_at = started_at or datetime.now(UTC)
    target = str(experiment.get("target_service")) if experiment and experiment.get("target_service") else None
    window_start = started_at - timedelta(seconds=request.lookback_seconds)
    window_end = started_at + timedelta(seconds=request.window_seconds)

    relevant = []
    for event in buffer.telemetry:
        timestamp = parse_timestamp(event.get("timestamp")) or parse_timestamp(event.get("ingestion_timestamp"))
        if timestamp is None or timestamp < window_start or timestamp > window_end:
            continue
        flags = event.get("anomaly_flags") or []
        if flags:
            relevant.append((timestamp, event))

    first_by_service: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for timestamp, event in sorted(relevant, key=lambda item: item[0]):
        service = event.get("service_name") or event.get("pod_name")
        if not service:
            continue
        first_by_service.setdefault(str(service), (timestamp, event))

    affected = list(first_by_service.keys())
    chain = []
    if target:
        chain.append(target)
    for service in affected:
        if service not in chain:
            chain.append(service)

    target_event = first_by_service.get(target or "")
    if target_event and len(affected) > 1:
        confidence = "high"
    elif target_event:
        confidence = "medium"
    elif affected:
        confidence = "low"
    else:
        confidence = "low"

    evidence = [
        {
            "timestamp": timestamp.isoformat(),
            "service": service,
            "anomaly_flags": event.get("anomaly_flags", []),
            "derived_status": event.get("derived_status"),
            "pod_name": event.get("pod_name"),
        }
        for service, (timestamp, event) in first_by_service.items()
    ]

    return IncidentRecord(
        experiment_id=request.experiment_id,
        root_cause_service=target or (affected[0] if affected else None),
        causal_chain=chain,
        affected_services=affected,
        confidence=confidence,
        evidence=evidence,
        started_at=started_at,
    )


def _find_experiment(experiment_id: str, buffer: EventBuffer) -> dict[str, Any] | None:
    for event in reversed(buffer.experiments):
        if event.get("experiment_id") == experiment_id:
            return event
    return None
