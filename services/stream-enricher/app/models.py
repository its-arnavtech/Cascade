from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DerivedStatus = Literal["healthy", "warning", "degraded"]
AnomalyFlag = Literal[
    "high_cpu",
    "high_memory",
    "unstable",
    "degraded",
    "high_error_rate",
    "high_latency",
    "not_ready",
    "service_unavailable",
    "warning_events",
    "dependency_unhealthy",
    "insufficient_data",
]


class Settings(BaseSettings):
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_raw_topic: str = "telemetry.raw"
    kafka_enriched_topic: str = "telemetry.enriched"
    kafka_consumer_group: str = "stream-enricher"
    high_memory_threshold_bytes: float = 512 * 1024 * 1024

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


class TelemetryRawEvent(BaseModel):
    event_id: str
    timestamp: datetime
    namespace: str
    pod_name: str
    service_name: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    cpu: float | None = None
    memory: float | None = None
    restart_count: float | None = None
    pod_phase: str | None = None
    ready: bool | None = None
    request_rate: float | None = None
    error_rate: float | None = None
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    latency_p99_ms: float | None = None
    warning_event_count: float | None = None
    service_available: bool | None = None
    redpanda_healthy: bool | None = None
    clickhouse_healthy: bool | None = None
    qdrant_healthy: bool | None = None
    missing_metrics: list[str] = Field(default_factory=list)
    collection_warnings: list[str] = Field(default_factory=list)
    metric_status: dict[str, str] = Field(default_factory=dict)
    evidence_quality: str = "insufficient_data"
    used_kubernetes_fallback: bool = False
    source: str


class NormalizedFields(BaseModel):
    cpu_percent: float | None = Field(default=None, description="CPU cores normalized to percentage of one core.")
    memory_mib: float | None = Field(default=None, description="Memory bytes normalized to mebibytes.")
    restart_count: int = 0
    request_rate: float | None = None
    error_rate: float | None = None
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    latency_p99_ms: float | None = None
    warning_event_count: float | None = None
    ready: bool | None = None
    service_available: bool | None = None
    redpanda_healthy: bool | None = None
    clickhouse_healthy: bool | None = None
    qdrant_healthy: bool | None = None
    missing_metrics: list[str] = Field(default_factory=list)
    collection_warnings: list[str] = Field(default_factory=list)
    metric_status: dict[str, str] = Field(default_factory=dict)
    evidence_quality: str = "insufficient_data"
    used_kubernetes_fallback: bool = False


class TelemetryEnrichedEvent(TelemetryRawEvent):
    anomaly_flags: list[AnomalyFlag]
    ingestion_timestamp: datetime
    normalized_fields: NormalizedFields
    derived_status: DerivedStatus


class HealthResponse(BaseModel):
    status: str
    service: str
