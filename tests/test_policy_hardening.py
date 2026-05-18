from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

from services.shared.chaos.safety import default_policy as chaos_policy
from services.shared.chaos.safety import validate_plan as validate_chaos_plan
from services.shared.chaos.templates import build_manifest
from services.shared.remediation.approval import is_approval_current
from services.shared.remediation.planner import build_plan
from services.shared.remediation.safety import default_policy as remediation_policy
from services.shared.remediation.safety import validate_plan as validate_remediation_plan
from services.shared.remediation.schemas import RemediationPlanRequest


def _load_module(name: str, path: str):
    module_path = Path(__file__).resolve().parents[1] / path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _chaos_plan(service: str = "catalogue") -> dict:
    manifest = build_manifest("pod_kill", "chaos_exp_hardening", "cascade-targets", service, 30)
    return {
        "plan_id": "chaos_plan_hardening",
        "experiment_id": "chaos_exp_hardening",
        "experiment_kind": "pod_kill",
        "target_namespace": "cascade-targets",
        "target_service": service,
        "target_selector": manifest["spec"]["selector"],
        "duration_seconds": 30,
        "manifest": manifest,
    }


def _remediation_plan(action_type: str = "restart_deployment") -> dict:
    request = RemediationPlanRequest(service="catalogue", namespace="cascade-targets", preferred_action_type=action_type)
    return build_plan(request, [{"source": "test", "type": "anomaly", "id": "a1"}], {"summary": "evidence"})


def test_approval_expiry_fails_closed() -> None:
    future = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    assert is_approval_current({"decision": "approved", "expires_at": future})
    assert not is_approval_current({"decision": "approved", "expires_at": past})
    assert not is_approval_current({"decision": "approved"})
    assert not is_approval_current({"decision": "approved", "expires_at": "not-a-date"})


def test_chaos_rejects_database_and_protected_services() -> None:
    result = validate_chaos_plan(_chaos_plan("catalogue-db"), chaos_policy(), approved=True, dry_run=False)

    assert not result.allowed
    assert any("protected" in item for item in result.violations)
    assert any("allowlisted" in item for item in result.violations)


def test_chaos_rejects_denied_resource_kind_and_wildcard_selector() -> None:
    plan = _chaos_plan()
    plan["manifest"]["kind"] = "Namespace"
    plan["target_selector"] = {"namespaces": ["*"], "labelSelectors": {"app": "*"}}

    result = validate_chaos_plan(plan, chaos_policy(), approved=True, dry_run=False)

    assert not result.allowed
    assert any("Resource kind 'Namespace' is denied" in item for item in result.violations)
    assert any("Wildcard selectors" in item for item in result.violations)


def test_remediation_requires_rollback_and_post_checks_for_execution() -> None:
    plan = _remediation_plan("restart_deployment")
    plan["rollback_steps"] = []
    plan["plan"]["post_checks"] = []

    result = validate_remediation_plan(plan, remediation_policy(), approved=True, dry_run=False, execution_enabled=True)

    assert not result.allowed
    assert any("Rollback steps" in item for item in result.violations)
    assert any("Post-checks" in item for item in result.violations)


def test_remediation_rejects_denied_resource_kind_wildcard_and_unmanaged_cleanup() -> None:
    plan = _remediation_plan("cleanup_cascade_chaos_resource")
    plan["selector"] = {"matchLabels": {"app": "*"}}
    plan["dry_run_manifest"]["metadata"]["labels"] = {"cascade.io/phase": "phase7"}

    result = validate_remediation_plan(plan, remediation_policy())

    assert not result.allowed
    assert any("Wildcard selectors" in item or "Broad selectors" in item for item in result.violations)
    assert any("managed phase7 labels" in item for item in result.violations)

    plan = _remediation_plan("investigate_only")
    plan["dry_run_manifest"] = {"kind": "Namespace", "metadata": {"name": "cascade-targets"}}
    result = validate_remediation_plan(plan, remediation_policy())
    assert not result.allowed
    assert any("namespaces cannot be mutated" in item for item in result.violations)


def test_policy_api_exposes_explicit_denied_and_protected_fields() -> None:
    fake_client = types.SimpleNamespace(ApiException=Exception)
    fake_config = types.SimpleNamespace()
    sys.modules.setdefault("kubernetes", types.SimpleNamespace(client=fake_client, config=fake_config))
    sys.modules.setdefault("kubernetes.client", fake_client)
    sys.modules.setdefault("kubernetes.config", fake_config)

    class FakeAIOKafkaProducer:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

        async def send_and_wait(self, *args, **kwargs):
            return types.SimpleNamespace(topic="", partition=0, offset=0)

    sys.modules.setdefault("aiokafka", types.SimpleNamespace(AIOKafkaProducer=FakeAIOKafkaProducer))
    chaos_executor = _load_module("chaos_executor_hardening", "services/chaos-executor-service/app/main.py")
    remediation_executor = _load_module("remediation_executor_hardening", "services/remediation-executor-service/app/main.py")

    chaos_response = asyncio.run(chaos_executor.safety_policy())
    remediation_response = asyncio.run(remediation_executor.safety_policy())

    assert "denied" in chaos_response
    assert "protected" in chaos_response
    assert "resource_kinds" in chaos_response["denied"]
    assert "denied" in remediation_response
    assert "protected" in remediation_response
    assert "services" in remediation_response["protected"]
