from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InvestigationRequest(BaseModel):
    trigger_type: str = Field(default="manual", pattern="^(anomaly|incident|service|manual)$")
    trigger_id: str | None = None
    service: str | None = None
    namespace: str = "cascade-targets"
    objective: str = "Investigate current Cascade operational signals"
    mode: str = Field(default="deterministic", pattern="^(deterministic|langgraph)$")
    max_steps: int = Field(default=12, ge=3, le=30)


class ToolResponse(BaseModel):
    tool_name: str
    status: str = "ok"
    data: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: float = 0.0
    error: str | None = None


class AgentState(BaseModel):
    investigation_id: str
    trigger: InvestigationRequest
    anomaly_refs: list[dict[str, Any]] = Field(default_factory=list)
    incident_refs: list[dict[str, Any]] = Field(default_factory=list)
    telemetry_evidence: list[dict[str, Any]] = Field(default_factory=list)
    topology_evidence: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_evidence: list[dict[str, Any]] = Field(default_factory=list)
    timeline_evidence: list[dict[str, Any]] = Field(default_factory=list)
    tool_call_history: list[dict[str, Any]] = Field(default_factory=list)
    conclusions: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    recommended_next_steps: list[str] = Field(default_factory=list)
    suggested_remediation: list[str] = Field(default_factory=list)
