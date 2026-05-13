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
    pod_phase: str | None = None
    cpu_usage_cores: float | None = None
    memory_working_set_bytes: float | None = None
    restart_count: float | None = None


class SnapshotResponse(BaseModel):
    namespace: str
    timestamp: datetime
    pods: list[TelemetryPodSnapshot]


class RawMetricsResponse(BaseModel):
    query: str
    prometheus: dict[str, Any]


class ErrorResponse(BaseModel):
    detail: str
