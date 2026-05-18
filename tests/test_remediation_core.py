from __future__ import annotations

import unittest
from pathlib import Path

from services.shared.agents.tool_contracts import MUTATING_TOOL_NAMES, TOOL_REGISTRY
from services.shared.remediation.events import remediation_event
from services.shared.remediation.planner import build_plan
from services.shared.remediation.safety import default_policy, validate_approval, validate_plan
from services.shared.remediation.schemas import RemediationPlanRequest


class Phase8CoreTests(unittest.TestCase):
    def _plan(self, action_type: str = "investigate_only", namespace: str = "cascade-targets", evidence: bool = True) -> dict:
        request = RemediationPlanRequest(
            trigger_type="manual",
            service="catalogue",
            namespace=namespace,
            objective="Recommend safe remediation",
            preferred_action_type=action_type,
        )
        refs = [{"source": "test", "type": "anomaly", "id": "a1"}] if evidence else []
        return build_plan(request, refs, {"summary": "test evidence", "severity": "warning"})

    def test_safety_rejects_denied_namespace(self) -> None:
        result = validate_plan(self._plan(namespace="kube-system"), default_policy())
        self.assertFalse(result.allowed)
        self.assertTrue(any("denied" in item for item in result.violations))

    def test_safety_rejects_unsupported_action_type(self) -> None:
        plan = self._plan()
        plan["action_type"] = "patch_secret"
        result = validate_plan(plan, default_policy())
        self.assertFalse(result.allowed)
        self.assertTrue(any("unsupported" in item for item in result.violations))

    def test_safety_requires_approval_for_real_execution(self) -> None:
        result = validate_plan(self._plan("restart_deployment"), default_policy(), approved=False, dry_run=False, execution_enabled=True)
        self.assertFalse(result.allowed)
        self.assertTrue(any("approval" in item for item in result.violations))

    def test_real_execution_disabled_by_default(self) -> None:
        result = validate_plan(self._plan("scale_deployment_noop"), default_policy(), approved=True, dry_run=False, execution_enabled=False)
        self.assertFalse(result.allowed)
        self.assertTrue(any("EXECUTION_ENABLED=false" in item for item in result.violations))

    def test_safety_allows_investigate_only_with_evidence(self) -> None:
        result = validate_plan(self._plan("investigate_only"), default_policy())
        self.assertTrue(result.allowed)
        self.assertEqual(result.risk_level, "low")

    def test_plan_generation_includes_rollback_and_evidence(self) -> None:
        plan = self._plan("investigate_only")
        self.assertGreaterEqual(len(plan["rollback_steps"]), 1)
        self.assertGreaterEqual(len(plan["evidence_refs"]), 1)
        self.assertGreater(plan["confidence"], 0)

    def test_approval_requires_explicit_decision_and_rejection_reason(self) -> None:
        self.assertTrue(validate_approval("rejected", "local-user", ""))
        self.assertFalse(validate_approval("approved", "local-user", "Reviewed"))

    def test_event_schema_builder_is_compact(self) -> None:
        plan = self._plan()
        event = remediation_event("remediation.plan.created", plan=plan, summary="created")
        self.assertEqual(event["schema_version"], "phase8.v1")
        self.assertEqual(event["event_type"], "remediation.plan.created")
        self.assertEqual(event["plan_id"], plan["plan_id"])
        self.assertNotIn("dry_run_manifest", event)

    def test_agent_gateway_has_read_only_tools_only(self) -> None:
        self.assertIn("get_recent_remediation_plans", TOOL_REGISTRY)
        self.assertIn("get_remediation_safety_policy", TOOL_REGISTRY)
        self.assertNotIn("approve_remediation", TOOL_REGISTRY)
        self.assertNotIn("execute_remediation", TOOL_REGISTRY)
        self.assertIn("execute_remediation", MUTATING_TOOL_NAMES)

    def test_rbac_manifest_has_no_cluster_admin_or_secret_access(self) -> None:
        text = Path("infra/kubernetes/remediation-executor-service/rbac.yaml").read_text(encoding="utf-8")
        self.assertNotIn("cluster-admin", text)
        self.assertNotIn("secrets", text.lower())
        self.assertNotIn("configmaps", text.lower())
        self.assertIn("namespace: cascade-targets", text)


if __name__ == "__main__":
    unittest.main()
