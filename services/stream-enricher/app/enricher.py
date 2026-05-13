from __future__ import annotations

from datetime import UTC, datetime

from app.models import AnomalyFlag, NormalizedFields, Settings, TelemetryEnrichedEvent, TelemetryRawEvent


def enrich_event(raw_event: TelemetryRawEvent, settings: Settings) -> TelemetryEnrichedEvent:
    normalized_fields = _normalize(raw_event)
    anomaly_flags = _detect_anomalies(raw_event, normalized_fields, settings)
    derived_status = "degraded" if "degraded" in anomaly_flags else "warning" if anomaly_flags else "healthy"

    return TelemetryEnrichedEvent(
        **raw_event.model_dump(),
        anomaly_flags=anomaly_flags,
        ingestion_timestamp=datetime.now(UTC),
        normalized_fields=normalized_fields,
        derived_status=derived_status,
    )


def _normalize(raw_event: TelemetryRawEvent) -> NormalizedFields:
    restart_count = int(raw_event.restart_count or 0)
    return NormalizedFields(
        cpu_percent=round(raw_event.cpu * 100, 4) if raw_event.cpu is not None else None,
        memory_mib=round(raw_event.memory / (1024 * 1024), 4) if raw_event.memory is not None else None,
        restart_count=max(restart_count, 0),
    )


def _detect_anomalies(
    raw_event: TelemetryRawEvent,
    normalized_fields: NormalizedFields,
    settings: Settings,
) -> list[AnomalyFlag]:
    flags: list[AnomalyFlag] = []

    if normalized_fields.cpu_percent is not None and normalized_fields.cpu_percent > 80:
        flags.append("high_cpu")

    if raw_event.memory is not None and raw_event.memory > settings.high_memory_threshold_bytes:
        flags.append("high_memory")

    if normalized_fields.restart_count > 0:
        flags.append("unstable")

    if raw_event.pod_phase != "Running":
        flags.append("degraded")

    return flags
