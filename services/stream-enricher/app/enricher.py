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
        request_rate=raw_event.request_rate,
        error_rate=raw_event.error_rate,
        latency_p50_ms=raw_event.latency_p50_ms,
        latency_p95_ms=raw_event.latency_p95_ms,
        latency_p99_ms=raw_event.latency_p99_ms,
        warning_event_count=raw_event.warning_event_count,
        ready=raw_event.ready,
        service_available=raw_event.service_available,
        redpanda_healthy=raw_event.redpanda_healthy,
        clickhouse_healthy=raw_event.clickhouse_healthy,
        qdrant_healthy=raw_event.qdrant_healthy,
        missing_metrics=raw_event.missing_metrics,
        collection_warnings=raw_event.collection_warnings,
        metric_status=raw_event.metric_status,
        evidence_quality=raw_event.evidence_quality,
        used_kubernetes_fallback=raw_event.used_kubernetes_fallback,
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

    if raw_event.ready is False:
        flags.append("not_ready")

    if raw_event.service_available is False:
        flags.append("service_unavailable")

    if raw_event.error_rate is not None and raw_event.error_rate >= 0.05:
        flags.append("high_error_rate")

    if raw_event.latency_p95_ms is not None and raw_event.latency_p95_ms >= 500:
        flags.append("high_latency")

    if raw_event.warning_event_count is not None and raw_event.warning_event_count > 0:
        flags.append("warning_events")

    if any(value is False for value in (raw_event.redpanda_healthy, raw_event.clickhouse_healthy, raw_event.qdrant_healthy)):
        flags.append("dependency_unhealthy")

    if raw_event.missing_metrics:
        flags.append("insufficient_data")

    return sorted(set(flags))
