from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


class TopologyResponse(BaseModel):
    dependencies: dict[str, list[str]]


class ImpactRequest(BaseModel):
    root_service: str


class ImpactResponse(BaseModel):
    root_service: str
    impact_path: list[str]
    affected_services: list[str]


class DependenciesResponse(BaseModel):
    service_name: str
    direction: str
    hops: int
    dependencies: list[str]


class DirectionalServicesResponse(BaseModel):
    service_name: str
    upstream: list[str] | None = None
    downstream: list[str] | None = None


class BlastRadiusRequest(BaseModel):
    root_service: str
    hops: int = 3
    depth_cap: int = 4


class CriticalPathsRequest(BaseModel):
    root_service: str
    depth_cap: int = 4
    limit: int = 5


class TopologyRefreshRequest(BaseModel):
    persist: bool = False


class TrafficEdgeEvidence(BaseModel):
    source_service: str
    target_service: str
    namespace: str | None = None
    request_count: float | None = None
    error_count: float | None = None
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    latency_p99_ms: float | None = None
    observation_window: str | None = None
    evidence_source: str = "trace"
    confidence: float | None = None
    last_seen: str | None = None
    trace_id: str | None = None
    event_id: str | None = None


class TrafficInferenceRequest(BaseModel):
    evidence_source: str = "trace"
    edges: list[TrafficEdgeEvidence]
