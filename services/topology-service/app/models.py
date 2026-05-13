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
