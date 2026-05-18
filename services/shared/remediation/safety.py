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
    post_checks = _post_checks(plan)
    manifest = plan.get("dry_run_manifest") or {}

    if namespace in policy.denied_namespaces:
        violations.append(f"Namespace '{namespace}' is denied for remediation")
    if namespace not in policy.allowed_namespaces:
        violations.append(f"Namespace '{namespace}' is not allowlisted")
    if _contains_wildcard(namespace) or _contains_wildcard(service):
        violations.append("Wildcard namespaces and services are not allowed")
    if service in policy.denied_services:
        violations.append(f"Service '{service}' is denied for remediation")
    if service in policy.protected_services:
        violations.append(f"Service '{service}' is protected from remediation")
    if service and service not in policy.allowed_services:
        violations.append(f"Service '{service}' is not allowlisted")
    if action_type not in policy.supported_action_types:
        violations.append(f"Action type '{action_type}' is unsupported")
    if policy.require_evidence_for_plan and not evidence:
        violations.append("Evidence references are required before remediation can be recommended")
    if _has_broad_selector(plan):
        violations.append("Broad selectors are not allowed")
    if _contains_wildcard(plan.get("selector") or {}):
        violations.append("Wildcard selectors are not allowed")
    if _mutates_denied_kind(manifest, policy):
        violations.append("Secrets, ConfigMaps, RBAC, service accounts, and namespaces cannot be mutated")
    if action_type == "cleanup_cascade_chaos_resource" and not _has_required_cleanup_labels(manifest, policy):
        violations.append("Cascade chaos cleanup requires managed phase7 labels")
    if not dry_run:
        if policy.require_approval_for_execution and not approved:
            violations.append("Real remediation execution requires a valid human approval")
        if not execution_enabled:
            violations.append("Real remediation execution is disabled by EXECUTION_ENABLED=false")
        if action_type not in policy.executable_action_types:
            violations.append(f"Action type '{action_type}' is not executable")
        if policy.require_rollback_for_execution and not rollback:
            violations.append("Rollback steps are required before execution")
        if policy.require_post_checks_for_execution and not post_checks:
            violations.append("Post-checks are required before execution")

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
        namespaces = selector.get("namespaces") or []
        return not labels or _contains_wildcard(labels) or _contains_wildcard(namespaces)
    action_type = str(plan.get("action_type") or "")
    return action_type in {"restart_deployment", "scale_deployment_noop"} and not str(plan.get("service") or "")


def _mutates_denied_kind(manifest: dict[str, Any], policy: RemediationPolicy) -> bool:
    kind = str(manifest.get("kind") or "")
    return kind in set(policy.denied_resource_kinds)


def _has_required_cleanup_labels(manifest: dict[str, Any], policy: RemediationPolicy) -> bool:
    labels = manifest.get("metadata", {}).get("labels", {})
    return all(labels.get(key) == value for key, value in policy.cascade_chaos_cleanup_labels.items())


def _post_checks(plan: dict[str, Any]) -> list[Any]:
    checks = plan.get("post_checks")
    if checks is None:
        checks = (plan.get("plan") or {}).get("post_checks")
    if checks is None:
        checks = ((plan.get("plan") or {}).get("plan") or {}).get("post_checks")
    return checks or []


def _contains_wildcard(value: Any) -> bool:
    if isinstance(value, str):
        return "*" in value
    if isinstance(value, dict):
        return any(_contains_wildcard(key) or _contains_wildcard(item) for key, item in value.items())
    if isinstance(value, list | tuple | set):
        return any(_contains_wildcard(item) for item in value)
    return False


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

