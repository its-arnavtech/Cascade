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
