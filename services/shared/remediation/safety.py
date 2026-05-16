from __future__ import annotations

from typing import Any

from .schemas import RemediationPolicy, SafetyResult


def default_policy() -> RemediationPolicy:
    return RemediationPolicy()


def validate_plan(
    plan: dict[str, Any],
    policy: RemediationPolicy | None = None,
    *,
    approved: bool = False,
    dry_run: bool = True,
    execution_enabled: bool = False,
) -> SafetyResult:
    policy = policy or default_policy()
    violations: list[str] = []
    findings: list[str] = []
    namespace = str(plan.get("namespace") or plan.get("target_namespace") or "")
    service = str(plan.get("service") or plan.get("target_service") or "")
    action_type = str(plan.get("action_type") or "")
    evidence = plan.get("evidence_refs") or []
    rollback = plan.get("rollback_steps") or []
    manifest = plan.get("dry_run_manifest") or {}

    if namespace in policy.denied_namespaces:
        violations.append(f"Namespace '{namespace}' is denied for remediation")
    if namespace not in policy.allowed_namespaces:
        violations.append(f"Namespace '{namespace}' is not allowlisted")
    if service and service not in policy.allowed_services:
        violations.append(f"Service '{service}' is not allowlisted")
    if action_type not in policy.supported_action_types:
        violations.append(f"Action type '{action_type}' is unsupported")
    if policy.require_evidence_for_plan and not evidence:
        violations.append("Evidence references are required before remediation can be recommended")
    if _has_broad_selector(plan):
        violations.append("Broad selectors are not allowed")
    if _mutates_denied_kind(manifest, policy):
        violations.append("Secrets, ConfigMaps, RBAC, service accounts, and namespaces cannot be mutated")
    if not dry_run:
        if policy.require_approval_for_execution and not approved:
            violations.append("Real remediation execution requires a valid human approval")
        if not execution_enabled:
            violations.append("Real remediation execution is disabled by EXECUTION_ENABLED=false")
        if action_type not in policy.executable_action_types:
            violations.append(f"Action type '{action_type}' is not executable")
        if policy.require_rollback_for_execution and not rollback:
            violations.append("Rollback steps are required before execution")

    if not violations:
        findings.append("Action is bounded by deny-by-default remediation policy")
        findings.append("Target namespace and service are explicitly allowlisted")
        if dry_run:
            findings.append("Validation is dry-run only and does not mutate cluster state")
        elif action_type == "scale_deployment_noop":
            findings.append("Execution template is a no-op scale validation")
    risk = _risk_score(violations, action_type, bool(evidence))
    return SafetyResult(allowed=not violations, risk_level=_risk_level(risk, violations), risk_score=risk, findings=findings, violations=violations)


def validate_approval(decision: str, approver: str, reason: str) -> list[str]:
    violations: list[str] = []
    if decision not in {"approved", "rejected"}:
        violations.append("Decision must be approved or rejected")
    if not approver.strip():
        violations.append("Approver is required")
    if decision == "rejected" and not reason.strip():
        violations.append("Rejection requires a reason")
    return violations


def _has_broad_selector(plan: dict[str, Any]) -> bool:
    selector = plan.get("selector") or {}
    if selector:
        labels = selector.get("matchLabels") or selector.get("labelSelectors") or {}
        return not labels or "*" in labels.values()
    action_type = str(plan.get("action_type") or "")
    return action_type in {"restart_deployment", "scale_deployment_noop"} and not str(plan.get("service") or "")


def _mutates_denied_kind(manifest: dict[str, Any], policy: RemediationPolicy) -> bool:
    kind = str(manifest.get("kind") or "")
    return kind in set(policy.denied_resource_kinds)


def _risk_score(violations: list[str], action_type: str, has_evidence: bool) -> float:
    if violations:
        return max(0.0, round(0.75 + 0.05 * len(violations), 2))
    base = {"investigate_only": 0.05, "scale_deployment_noop": 0.08, "restart_deployment": 0.22, "rollback_deployment": 0.35, "cleanup_cascade_chaos_resource": 0.18}.get(action_type, 0.8)
    if not has_evidence:
        base += 0.2
    return round(min(1.0, base), 2)


def _risk_level(risk: float, violations: list[str]) -> str:
    if violations:
        return "rejected"
    if risk <= 0.1:
        return "low"
    if risk <= 0.3:
        return "medium"
    return "high"

