from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class TelemetryPodSnapshot(BaseModel):
    service_name: str | None = Field(default=None, description="Best-effort workload name inferred from the pod.")
    pod_name: str
    namespace: str
    labels: dict[str, str] = Field(default_factory=dict)
    pod_phase: str | None = None
    cpu_usage_cores: float | None = None
    memory_working_set_bytes: float | None = None
    restart_count: float | None = None
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


class SnapshotResponse(BaseModel):
    namespace: str
    timestamp: datetime
    pods: list[TelemetryPodSnapshot]
    query_status: dict[str, dict[str, Any]] = Field(default_factory=dict)
    missing_metrics: list[str] = Field(default_factory=list)
    collection_warnings: list[str] = Field(default_factory=list)
    used_kubernetes_fallback: bool = False


class RawMetricsResponse(BaseModel):
    query: str
    prometheus: dict[str, Any] | None = None
    query_status: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    detail: str
