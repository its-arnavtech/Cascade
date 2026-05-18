from __future__ import annotations

from dataclasses import dataclass

from services.shared.targets.catalog import ACTIVE_NAMESPACE, ACTIVE_PROTECTED_SERVICES, ACTIVE_SAFE_CHAOS_SERVICES


@dataclass(frozen=True)
class LiveDemoConfig:
    enable_dangerous_actions: bool = False
    enable_real_chaos: bool = False
    enable_real_remediation: bool = False
    cascade_live_demo_mode: bool = False
    cascade_allowed_cluster_context: str = "kind-cascade"
    cascade_active_cluster_context: str = ""
    cascade_allowed_target_namespace: str = ACTIVE_NAMESPACE
    cascade_require_approval: bool = True
    cascade_require_dry_run_first: bool = True


def validate_live_demo_gate(
    *,
    action: str,
    namespace: str,
    service: str,
    config: LiveDemoConfig,
    feature_enabled: bool,
    approval_current: bool,
    dry_run_passed: bool,
    current_context: str = "",
) -> list[str]:
    violations: list[str] = []
    active_context = config.cascade_active_cluster_context or current_context

    if not config.enable_dangerous_actions:
        violations.append("Live demo execution requires ENABLE_DANGEROUS_ACTIONS=true")
    if not feature_enabled:
        violations.append(f"Live demo execution requires {action}=true")
    if not config.cascade_live_demo_mode:
        violations.append("Live demo execution requires CASCADE_LIVE_DEMO_MODE=true")
    if not active_context:
        violations.append("Live demo execution requires an explicit active cluster context")
    elif active_context != config.cascade_allowed_cluster_context:
        violations.append(f"Cluster context '{active_context}' is not allowlisted for local demo execution")
    if namespace != config.cascade_allowed_target_namespace:
        violations.append(f"Namespace '{namespace}' is not the configured live demo target namespace")
    if namespace != ACTIVE_NAMESPACE:
        violations.append(f"Namespace '{namespace}' is not the active target namespace")
    if service not in ACTIVE_SAFE_CHAOS_SERVICES:
        violations.append(f"Service '{service}' is not allowlisted for live demo execution")
    if service in ACTIVE_PROTECTED_SERVICES:
        violations.append(f"Service '{service}' is protected from live demo execution")
    if config.cascade_require_approval and not approval_current:
        violations.append("Live demo execution requires a non-expired approval record")
    if config.cascade_require_dry_run_first and not dry_run_passed:
        violations.append("Live demo execution requires a prior successful dry-run for the same plan")

    return violations
