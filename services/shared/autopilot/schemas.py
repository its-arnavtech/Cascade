from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AutopilotMode(StrEnum):
    READ_ONLY = "read_only"
    DRY_RUN = "dry_run"
    LOCAL_DEMO_EXECUTE = "local_demo_execute"


class AutopilotState(StrEnum):
    REQUESTED = "requested"
    DETECTING = "detecting"
    INVESTIGATING = "investigating"
    EVIDENCE_BUNDLED = "evidence_bundled"
    RECOMMENDING = "recommending"
    POLICY_CHECKING = "policy_checking"
    DRY_RUNNING = "dry_running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    APPLYING = "applying"
    VERIFYING = "verifying"
    FIXED = "fixed"
    DEGRADED = "degraded"
    UNCHANGED = "unchanged"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class AutopilotResult(StrEnum):
    FIXED = "fixed"
    DEGRADED = "degraded"
    UNCHANGED = "unchanged"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class AutopilotRunRequest(BaseModel):
    trigger_type: str = Field(default="latest_anomaly", pattern="^(latest_anomaly|anomaly|service|manual)$")
    trigger_id: str = ""
    service: str = ""
    namespace: str = "cascade-targets"
    objective: str = "Run a safe Autopilot reliability loop"
    mode: AutopilotMode = AutopilotMode.DRY_RUN
    preferred_action_type: str = "investigate_only"


class AutopilotRunRecord(BaseModel):
    run_id: str
    created_at: str
    updated_at: str
    completed_at: str | None = None
    status: str
    final_result: str = ""
    mode: str
    trigger_type: str
    trigger_id: str = ""
    service: str = ""
    namespace: str = "cascade-targets"
    objective: str = ""
    anomaly_id: str = ""
    investigation_id: str = ""
    remediation_plan_id: str = ""
    approval_id: str = ""
    dry_run_execution_id: str = ""
    execution_id: str = ""
    proposed_action: str = ""
    error_message: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommendation: dict[str, Any] = Field(default_factory=dict)
    action: dict[str, Any] = Field(default_factory=dict)
    verification: dict[str, Any] = Field(default_factory=dict)


class AutopilotStepRecord(BaseModel):
    step_id: str
    run_id: str
    created_at: str
    state: str
    status: str
    summary: str
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""
