from __future__ import annotations

from services.shared.policy import AutonomyLevel, PolicyAction, evaluate_action_policy


def _action(**overrides):
    data = {
        "action_type": "restart_deployment",
        "target_namespace": "cascade-targets",
        "target_service": "catalogue",
        "target_deployment": "catalogue",
        "risk_level": "low",
        "blast_radius": 1,
        "rollback_available": True,
        "post_checks_available": True,
        "dry_run": False,
    }
    data.update(overrides)
    return PolicyAction(**data)


def test_read_only_action_allowed_at_level_zero() -> None:
    decision = evaluate_action_policy(
        _action(action_type="investigate_only", dry_run=True, rollback_available=False, post_checks_available=False),
        mode="read-only",
        autonomy_level=AutonomyLevel.READ_ONLY,
    )

    assert decision.allowed is True
    assert decision.status == "allowed"


def test_mutating_action_is_dry_run_only_at_level_two() -> None:
    decision = evaluate_action_policy(
        _action(dry_run=True),
        mode="dry-run",
        autonomy_level=AutonomyLevel.DRY_RUN_FIXES,
    )

    assert decision.allowed is True
    assert decision.status == "dry_run_only"
    assert decision.dry_run_only is True


def test_protected_service_and_wildcard_are_blocked() -> None:
    decision = evaluate_action_policy(
        _action(target_service="*", selector={"matchLabels": {"app": "*"}}),
        mode="local-demo",
        autonomy_level=AutonomyLevel.APPROVAL_FOR_RISKY,
        dangerous_actions_enabled=True,
        local_demo_enabled=True,
    )

    assert decision.allowed is False
    assert decision.status == "blocked"
    assert any("Wildcard" in reason for reason in decision.reasons)


def test_risky_real_action_requires_approval() -> None:
    decision = evaluate_action_policy(
        _action(risk_level="high", blast_radius=2),
        mode="production-safe",
        autonomy_level=AutonomyLevel.APPROVAL_FOR_RISKY,
        dangerous_actions_enabled=True,
    )

    assert decision.allowed is True
    assert decision.status == "requires_approval"
    assert decision.requires_approval is True


def test_local_demo_approved_action_can_be_allowed_automatically() -> None:
    decision = evaluate_action_policy(
        _action(approved=True),
        mode="local-demo",
        autonomy_level=AutonomyLevel.APPROVAL_FOR_RISKY,
        dangerous_actions_enabled=True,
        local_demo_enabled=True,
    )

    assert decision.allowed is True
    assert decision.status == "allowed_automatic"
    assert decision.allowed_automatically is True


def test_dangerous_real_action_blocked_when_flags_disabled() -> None:
    decision = evaluate_action_policy(
        _action(approved=True),
        mode="production-safe",
        autonomy_level=AutonomyLevel.APPROVAL_FOR_RISKY,
        dangerous_actions_enabled=False,
    )

    assert decision.allowed is False
    assert any("dangerous-action" in reason for reason in decision.reasons)


def test_action_budget_blocks_real_mutation_but_not_dry_run() -> None:
    blocked = evaluate_action_policy(
        _action(approved=True),
        mode="local-demo",
        autonomy_level=AutonomyLevel.APPROVAL_FOR_RISKY,
        dangerous_actions_enabled=True,
        local_demo_enabled=True,
        actions_used=3,
    )
    dry_run = evaluate_action_policy(
        _action(dry_run=True),
        mode="dry-run",
        autonomy_level=AutonomyLevel.DRY_RUN_FIXES,
        actions_used=3,
    )

    assert blocked.allowed is False
    assert any("Action budget exhausted" in reason for reason in blocked.reasons)
    assert dry_run.allowed is True
