from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from services.shared.targets.catalog import ACTIVE_NAMESPACE, ACTIVE_PROTECTED_SERVICES, ACTIVE_SAFE_CHAOS_SERVICES


class RemediationPlanRequest(BaseModel):
    trigger_type: str = Field(default="manual", pattern="^(anomaly|incident|investigation|chaos|manual)$")
    trigger_id: str = ""
    service: str = "catalogue"
    namespace: str = ACTIVE_NAMESPACE
    objective: str = "Recommend safe remediation next steps"
    preferred_action_type: str = "investigate_only"


class ApprovalRequest(BaseModel):
    plan_id: str
    decision: str = Field(pattern="^(approved|rejected)$")
    approver: str
    approver_role: str = "developer"
    reason: str = ""
    expires_minutes: int = Field(default=60, ge=1, le=1440)


class ExecutionRequest(BaseModel):
    plan_id: str
    approval_id: str = ""
    dry_run: bool = False


VerificationStatus = Literal["fixed", "improved", "unchanged", "degraded", "failed", "rolled_back", "insufficient_evidence"]
RollbackStatus = Literal["not_needed", "available", "unavailable", "executed", "failed", "disabled"]


class RemediationPolicy(BaseModel):
    allowed_namespaces: list[str] = Field(default_factory=lambda: [ACTIVE_NAMESPACE])
    denied_namespaces: list[str] = Field(default_factory=lambda: ["kube-system", "kube-public", "kube-node-lease", "local-path-storage", "monitoring", "cascade-system", "default"])
    allowed_services: list[str] = Field(default_factory=lambda: list(ACTIVE_SAFE_CHAOS_SERVICES))
    denied_services: list[str] = Field(default_factory=lambda: ["clickhouse", "redpanda", "qdrant", "postgres", "postgresql", "mysql", "mongodb", "kafka"])
    protected_services: list[str] = Field(default_factory=lambda: list(ACTIVE_PROTECTED_SERVICES) + ["clickhouse", "redpanda", "qdrant", "prometheus", "grafana", "chaos-controller-manager"])
    supported_action_types: list[str] = Field(default_factory=lambda: ["investigate_only", "restart_deployment", "scale_deployment_noop", "rollback_deployment", "cleanup_cascade_chaos_resource"])
    executable_action_types: list[str] = Field(default_factory=lambda: ["restart_deployment", "scale_deployment_noop", "cleanup_cascade_chaos_resource"])
    text_only_action_types: list[str] = Field(default_factory=lambda: ["investigate_only", "rollback_deployment"])
    denied_resource_kinds: list[str] = Field(default_factory=lambda: ["Secret", "ConfigMap", "Role", "RoleBinding", "ClusterRole", "ClusterRoleBinding", "ServiceAccount", "Namespace"])
    require_evidence_for_plan: bool = True
    require_approval_for_execution: bool = True
    require_rollback_for_execution: bool = True
    require_post_checks_for_execution: bool = True
    execution_enabled_default: bool = False
    cascade_chaos_cleanup_labels: dict[str, str] = Field(default_factory=lambda: {"cascade.io/phase": "phase7", "cascade.io/managed-by": "chaos-executor-service"})
    autonomy_level_default: int = 2
    action_budget: int = 3
    max_blast_radius: int = 3
    max_auto_blast_radius: int = 1


class SafetyResult(BaseModel):
    allowed: bool
    risk_level: str
    risk_score: float
    findings: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    policy_decision: dict[str, Any] = Field(default_factory=dict)


class RemediationPlan(BaseModel):
    plan_id: str
    status: str
    trigger_type: str
    trigger_id: str = ""
    source_investigation_id: str = ""
    source_anomaly_id: str = ""
    source_incident_id: str = ""
    source_chaos_run_id: str = ""
    service: str
    namespace: str
    severity: str = "unknown"
    risk_score: float = 0.0
    confidence: float = 0.0
    action_type: str = "investigate_only"
    action_summary: str = ""
    remediation_steps: list[str] = Field(default_factory=list)
    rollback_steps: list[str] = Field(default_factory=list)
    post_checks: list[str] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    safety_findings: list[str] = Field(default_factory=list)
    dry_run_manifest: dict[str, Any] = Field(default_factory=dict)
    policy_decision: dict[str, Any] = Field(default_factory=dict)
    plan: dict[str, Any] = Field(default_factory=dict)


class RollbackPlan(BaseModel):
    rollback_plan_id: str
    execution_id: str
    plan_id: str
    created_at: str
    updated_at: str
    action_type: str
    namespace: str
    service: str
    rollback_type: str = ""
    available: bool = False
    auto_executable: bool = False
    status: RollbackStatus = "unavailable"
    reason: str = ""
    snapshot: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    verification_id: str
    execution_id: str
    plan_id: str
    rollback_plan_id: str = ""
    created_at: str
    completed_at: str
    action_type: str
    namespace: str
    service: str
    status: VerificationStatus
    evidence_quality: str = "insufficient"
    rollback_status: RollbackStatus = "not_needed"
    summary: str = ""
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    comparisons: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    rollback: dict[str, Any] = Field(default_factory=dict)

