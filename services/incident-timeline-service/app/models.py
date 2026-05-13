from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class TimelineRequest(BaseModel):
    experiment: dict[str, Any] | None = None
    incident: dict[str, Any]
    topology_impact: dict[str, Any] | None = None


class TimelineEvent(BaseModel):
    timestamp: datetime
    event_type: str
    service: str | None = None
    message: str
    severity: str


class TimelineResponse(BaseModel):
    events: list[TimelineEvent]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReportRequest(TimelineRequest):
    pass


class IncidentReport(BaseModel):
    summary: str
    root_cause: str | None
    causal_chain: list[str]
    affected_services: list[str]
    evidence: list[dict[str, Any]]
    recommended_next_steps: list[str]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    markdown: str
