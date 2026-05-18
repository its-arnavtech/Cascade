from __future__ import annotations

from typing import Any

from .schemas import SafetyPolicy, SafetyResult


def default_policy() -> SafetyPolicy:
    return SafetyPolicy()


def validate_plan(plan: dict[str, Any], policy: SafetyPolicy | None = None, approved: bool = False, dry_run: bool = True) -> SafetyResult:
    policy = policy or default_policy()
    violations: list[str] = []
    findings: list[str] = []
    namespace = str(plan.get("target_namespace", ""))
    service = str(plan.get("target_service", ""))
    kind = str(plan.get("experiment_kind", ""))
    duration = int(plan.get("duration_seconds", 0))
    selector = plan.get("target_selector") or {}
    manifest = plan.get("manifest") or {}

    if namespace in policy.denied_namespaces:
        violations.append(f"Namespace '{namespace}' is denied for chaos execution")
    if namespace not in policy.allowed_namespaces:
        violations.append(f"Namespace '{namespace}' is not allowlisted")
    if _contains_wildcard(namespace) or _contains_wildcard(service):
        violations.append("Wildcard namespaces and services are not allowed")
    if service in policy.denied_services:
        violations.append(f"Service '{service}' is denied for chaos execution")
    if service in policy.protected_services:
        violations.append(f"Service '{service}' is protected from chaos execution")
    if service not in policy.allowed_services:
        violations.append(f"Service '{service}' is not allowlisted")
    if kind not in policy.supported_kinds:
        violations.append(f"Experiment kind '{kind}' is unsupported")
    resource_kind = str(manifest.get("kind") or plan.get("resource_kind") or "")
    if resource_kind in policy.denied_resource_kinds:
        violations.append(f"Resource kind '{resource_kind}' is denied for chaos execution")
    if resource_kind and resource_kind not in policy.supported_resource_kinds:
        violations.append(f"Resource kind '{resource_kind}' is unsupported for chaos execution")
    if duration <= 0 or duration > policy.max_duration_seconds:
        violations.append(f"Duration {duration}s exceeds max {policy.max_duration_seconds}s")
    if not dry_run and policy.require_approval_for_real_runs and not approved:
        violations.append("Real chaos execution requires approved=true")
    if _selector_is_broad(selector):
        violations.append("Target selector is broad or missing service labels")
    if _contains_wildcard(selector):
        violations.append("Wildcard selectors are not allowed")

    labels = manifest.get("metadata", {}).get("labels", {})
    for key, value in policy.required_labels.items():
        if labels.get(key) != value:
            violations.append(f"Required cleanup/safety label missing: {key}={value}")

    if not violations:
        findings.append("Plan is bounded to one allowlisted service in cascade-targets")
        findings.append("Only Chaos Mesh resources may be mutated by the executor")
    score = _score(violations, duration, kind)
    return SafetyResult(allowed=not violations, safety_score=score, risk_level=_risk(score), findings=findings, violations=violations)


def _selector_is_broad(selector: dict[str, Any]) -> bool:
    labels = selector.get("labelSelectors") or selector.get("labels") or {}
    namespaces = selector.get("namespaces") or []
    if not labels:
        return True
    if _contains_wildcard(labels) or labels.get("app") in (None, "", "*"):
        return True
    if _contains_wildcard(namespaces) or len(namespaces) != 1 or namespaces[0] != "cascade-targets":
        return True
    return False


def _contains_wildcard(value: Any) -> bool:
    if isinstance(value, str):
        return "*" in value
    if isinstance(value, dict):
        return any(_contains_wildcard(key) or _contains_wildcard(item) for key, item in value.items())
    if isinstance(value, list | tuple | set):
        return any(_contains_wildcard(item) for item in value)
    return False


def _score(violations: list[str], duration: int, kind: str) -> float:
    if violations:
        return max(0.0, round(0.55 - 0.12 * len(violations), 2))
    penalty = 0.0
    if duration > 60:
        penalty += 0.05
    if kind != "pod_kill":
        penalty += 0.05
    return round(max(0.0, min(1.0, 0.95 - penalty)), 2)


def _risk(score: float) -> str:
    if score >= 0.9:
        return "low"
    if score >= 0.75:
        return "medium"
    if score >= 0.5:
        return "high"
    return "rejected"
