from __future__ import annotations

from enum import IntEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from services.shared.targets.catalog import ACTIVE_NAMESPACE, ACTIVE_PROTECTED_SERVICES, ACTIVE_SAFE_CHAOS_SERVICES


PolicyMode = Literal["read-only", "dry-run", "local-demo", "production-safe"]
DecisionStatus = Literal["allowed", "blocked", "dry_run_only", "requires_approval", "allowed_automatic"]


class AutonomyLevel(IntEnum):
    READ_ONLY = 0
    RECOMMEND_ONLY = 1
    DRY_RUN_FIXES = 2
    AUTO_LOW_RISK = 3
    APPROVAL_FOR_RISKY = 4
    NEVER_ALLOWED = 5


class PolicyAction(BaseModel):
    action_type: str
    target_namespace: str = ACTIVE_NAMESPACE
    target_service: str = ""
    target_deployment: str = ""
    resource_kind: str = ""
    selector: dict[str, Any] = Field(default_factory=dict)
    blast_radius: int = 1
    risk_level: str = "unknown"
    risk_score: float = 0.0
    rollback_available: bool = False
    post_checks_available: bool = False
    dry_run: bool = True
    approved: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyConfig(BaseModel):
    allowed_namespaces: list[str] = Field(default_factory=lambda: [ACTIVE_NAMESPACE])
    denied_namespaces: list[str] = Field(default_factory=lambda: ["kube-system", "kube-public", "kube-node-lease", "local-path-storage", "monitoring", "cascade-system", "default"])
    allowed_services: list[str] = Field(default_factory=lambda: list(ACTIVE_SAFE_CHAOS_SERVICES))
    denied_services: list[str] = Field(default_factory=lambda: ["clickhouse", "redpanda", "qdrant", "postgres", "postgresql", "mysql", "mongodb", "kafka", "rabbitmq"])
    protected_services: list[str] = Field(default_factory=lambda: list(ACTIVE_PROTECTED_SERVICES) + ["clickhouse", "redpanda", "qdrant", "prometheus", "grafana", "chaos-controller-manager"])
    denied_resource_kinds: list[str] = Field(default_factory=lambda: ["Namespace", "Secret", "ConfigMap", "Role", "RoleBinding", "ClusterRole", "ClusterRoleBinding", "ServiceAccount", "PersistentVolumeClaim", "StatefulSet", "Job", "CronJob"])
    supported_actions: list[str] = Field(default_factory=lambda: [
        "investigate_only",
        "recommend_only",
        "restart_deployment",
        "scale_deployment",
        "scale_deployment_noop",
        "patch_resource",
        "rollback_deployment",
        "apply_config_patch",
        "run_chaos_experiment",
        "delete_pod",
        "evict_pod",
        "change_hpa",
        "cleanup_cascade_chaos_resource",
    ])
    read_only_actions: list[str] = Field(default_factory=lambda: ["investigate_only", "recommend_only"])
    dry_run_supported_actions: list[str] = Field(default_factory=lambda: [
        "restart_deployment",
        "scale_deployment",
        "scale_deployment_noop",
        "patch_resource",
        "rollback_deployment",
        "apply_config_patch",
        "run_chaos_experiment",
        "delete_pod",
        "evict_pod",
        "change_hpa",
        "cleanup_cascade_chaos_resource",
    ])
    local_demo_auto_actions: list[str] = Field(default_factory=lambda: ["restart_deployment", "scale_deployment_noop", "cleanup_cascade_chaos_resource", "run_chaos_experiment"])
    approval_required_actions: list[str] = Field(default_factory=lambda: ["restart_deployment", "scale_deployment", "patch_resource", "rollback_deployment", "apply_config_patch", "run_chaos_experiment", "delete_pod", "evict_pod", "change_hpa"])
    never_allowed_actions: list[str] = Field(default_factory=lambda: ["delete_namespace", "delete_deployment", "delete_statefulset", "patch_secret", "patch_configmap", "mutate_rbac", "database_change", "broker_change", "queue_change", "auth_store_change", "session_store_change"])
    action_autonomy_levels: dict[str, int] = Field(default_factory=lambda: {
        "investigate_only": 0,
        "recommend_only": 1,
        "restart_deployment": 3,
        "scale_deployment": 4,
        "scale_deployment_noop": 2,
        "patch_resource": 4,
        "rollback_deployment": 4,
        "apply_config_patch": 4,
        "run_chaos_experiment": 4,
        "delete_pod": 4,
        "evict_pod": 4,
        "change_hpa": 4,
        "cleanup_cascade_chaos_resource": 3,
    })
    max_blast_radius: int = 3
    max_auto_blast_radius: int = 1
    action_budget: int = 3
    cooldown_seconds: int = 300


class PolicyDecision(BaseModel):
    allowed: bool
    status: DecisionStatus
    action_type: str
    mode: PolicyMode
    autonomy_level: int
    required_autonomy_level: int
    risk_level: str
    risk_score: float
    blast_radius: int
    requires_approval: bool = False
    dry_run_only: bool = False
    allowed_automatically: bool = False
    rollback_available: bool = False
    reasons: list[str] = Field(default_factory=list)
    audit_record: dict[str, Any] = Field(default_factory=dict)


def default_policy_config() -> PolicyConfig:
    return PolicyConfig()


def evaluate_action_policy(
    action: PolicyAction,
    config: PolicyConfig | None = None,
    *,
    mode: PolicyMode = "dry-run",
    autonomy_level: int | AutonomyLevel = AutonomyLevel.DRY_RUN_FIXES,
    dangerous_actions_enabled: bool = False,
    local_demo_enabled: bool = False,
    actions_used: int = 0,
) -> PolicyDecision:
    config = config or default_policy_config()
    level = int(autonomy_level)
    required_level = _required_level(action.action_type, config)
    reasons: list[str] = []
    blocked: list[str] = []
    requires_approval = False
    risk_level = _normalize_risk(action)
    risk_score = _risk_score(action, risk_level)
    is_read_only = action.action_type in config.read_only_actions
    is_mutating = not is_read_only

    if action.action_type in config.never_allowed_actions or required_level >= int(AutonomyLevel.NEVER_ALLOWED):
        blocked.append(f"Action '{action.action_type}' is classified as never allowed")
    if action.action_type not in config.supported_actions and action.action_type not in config.never_allowed_actions:
        blocked.append(f"Action '{action.action_type}' is not supported by policy")
    if action.target_namespace in config.denied_namespaces:
        blocked.append(f"Namespace '{action.target_namespace}' is denied")
    if action.target_namespace not in config.allowed_namespaces:
        blocked.append(f"Namespace '{action.target_namespace}' is not allowlisted")
    if _contains_wildcard(action.target_namespace) or _contains_wildcard(action.target_service) or _contains_wildcard(action.target_deployment) or _contains_wildcard(action.selector):
        blocked.append("Wildcard namespace, service, deployment, or selector is not allowed")
    if action.target_service in config.denied_services:
        blocked.append(f"Service '{action.target_service}' is denied")
    if action.target_service in config.protected_services:
        blocked.append(f"Service '{action.target_service}' is protected")
    if action.target_service and action.target_service not in config.allowed_services:
        blocked.append(f"Service '{action.target_service}' is not allowlisted")
    if action.resource_kind in config.denied_resource_kinds:
        blocked.append(f"Resource kind '{action.resource_kind}' is denied")
    if action.blast_radius > config.max_blast_radius:
        blocked.append(f"Blast radius {action.blast_radius} exceeds max {config.max_blast_radius}")
    if is_mutating and not action.dry_run and actions_used >= config.action_budget:
        blocked.append(f"Action budget exhausted ({actions_used}/{config.action_budget})")
    if level < required_level and not (action.dry_run and action.action_type in config.dry_run_supported_actions and level >= int(AutonomyLevel.DRY_RUN_FIXES)):
        blocked.append(f"Autonomy level {level} is below required level {required_level} for {action.action_type}")
    if level <= int(AutonomyLevel.RECOMMEND_ONLY) and is_mutating:
        blocked.append(f"Autonomy level {level} permits recommendations only")

    if is_mutating and not action.dry_run and mode != "local-demo" and not dangerous_actions_enabled:
        blocked.append("Real mutating actions require explicit dangerous-action enablement")
    if is_mutating and not action.dry_run and mode == "local-demo" and not (dangerous_actions_enabled and local_demo_enabled):
        blocked.append("Local demo execution requires dangerous actions and local demo mode")
    if is_mutating and not action.rollback_available:
        if not action.dry_run:
            blocked.append("Rollback is required before real execution")
        else:
            reasons.append("Rollback is not available; action remains dry-run/recommendation only")
    if is_mutating and not action.post_checks_available and not action.dry_run:
        blocked.append("Post-checks are required before real execution")

    if blocked:
        return _decision(False, "blocked", action, mode, level, required_level, risk_level, risk_score, False, False, False, reasons + blocked)

    if is_read_only:
        reasons.append("Read-only/recommendation action is allowed")
        return _decision(True, "allowed", action, mode, level, required_level, risk_level, risk_score, False, False, False, reasons)

    if mode in {"read-only", "dry-run"} or action.dry_run or level == int(AutonomyLevel.DRY_RUN_FIXES):
        reasons.append("Policy permits dry-run validation but not real mutation in current mode/autonomy level")
        return _decision(True, "dry_run_only", action, mode, level, required_level, risk_level, risk_score, False, True, False, reasons)

    if action.action_type in config.approval_required_actions or risk_level in {"medium", "high", "critical"} or action.blast_radius > config.max_auto_blast_radius:
        requires_approval = not action.approved
    if requires_approval:
        reasons.append("Human approval is required by risk, action type, or blast radius")
        return _decision(True, "requires_approval", action, mode, level, required_level, risk_level, risk_score, True, False, False, reasons)

    if mode == "local-demo" and action.action_type in config.local_demo_auto_actions:
        reasons.append("Action is allowlisted for bounded local demo execution")
        return _decision(True, "allowed_automatic", action, mode, level, required_level, risk_level, risk_score, False, False, True, reasons)

    if level >= int(AutonomyLevel.AUTO_LOW_RISK) and risk_level == "low" and action.blast_radius <= config.max_auto_blast_radius:
        reasons.append("Low-risk action is within automatic autonomy and blast-radius limits")
        return _decision(True, "allowed_automatic", action, mode, level, required_level, risk_level, risk_score, False, False, True, reasons)

    reasons.append("Policy allows action after configured gates")
    return _decision(True, "allowed", action, mode, level, required_level, risk_level, risk_score, False, False, False, reasons)


def _decision(
    allowed: bool,
    status: DecisionStatus,
    action: PolicyAction,
    mode: PolicyMode,
    level: int,
    required_level: int,
    risk_level: str,
    risk_score: float,
    requires_approval: bool,
    dry_run_only: bool,
    automatic: bool,
    reasons: list[str],
) -> PolicyDecision:
    audit = {
        "action_type": action.action_type,
        "target_namespace": action.target_namespace,
        "target_service": action.target_service,
        "target_deployment": action.target_deployment,
        "resource_kind": action.resource_kind,
        "mode": mode,
        "autonomy_level": level,
        "required_autonomy_level": required_level,
        "status": status,
        "allowed": allowed,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "blast_radius": action.blast_radius,
        "requires_approval": requires_approval,
        "dry_run_only": dry_run_only,
        "allowed_automatically": automatic,
        "rollback_available": action.rollback_available,
        "reasons": reasons,
    }
    return PolicyDecision(
        allowed=allowed,
        status=status,
        action_type=action.action_type,
        mode=mode,
        autonomy_level=level,
        required_autonomy_level=required_level,
        risk_level=risk_level,
        risk_score=risk_score,
        blast_radius=action.blast_radius,
        requires_approval=requires_approval,
        dry_run_only=dry_run_only,
        allowed_automatically=automatic,
        rollback_available=action.rollback_available,
        reasons=reasons,
        audit_record=audit,
    )


def _required_level(action_type: str, config: PolicyConfig) -> int:
    if action_type in config.never_allowed_actions:
        return int(AutonomyLevel.NEVER_ALLOWED)
    return int(config.action_autonomy_levels.get(action_type, AutonomyLevel.NEVER_ALLOWED))


def _normalize_risk(action: PolicyAction) -> str:
    value = str(action.risk_level or "").lower()
    if value in {"critical", "high", "medium", "low"}:
        return value
    score = action.risk_score
    if score >= 0.75:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def _risk_score(action: PolicyAction, risk_level: str) -> float:
    if action.risk_score:
        return max(0.0, min(1.0, round(action.risk_score, 2)))
    return {"low": 0.1, "medium": 0.4, "high": 0.75, "critical": 0.95}.get(risk_level, 0.5)


def _contains_wildcard(value: Any) -> bool:
    if isinstance(value, str):
        return "*" in value
    if isinstance(value, dict):
        return any(_contains_wildcard(key) or _contains_wildcard(item) for key, item in value.items())
    if isinstance(value, list | tuple | set):
        return any(_contains_wildcard(item) for item in value)
    return False
