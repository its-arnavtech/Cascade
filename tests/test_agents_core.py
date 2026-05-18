from __future__ import annotations

import unittest

from services.shared.agents.deterministic_planner import build_plan
from services.shared.agents.reports import build_investigation_report, build_lifecycle_event, stable_id
from services.shared.agents.safety import ensure_read_only_tool, text_only_remediation
from services.shared.agents.schemas import AgentState, InvestigationRequest, ToolResponse
from services.shared.agents.tool_contracts import TOOL_REGISTRY


class Phase6CoreTests(unittest.TestCase):
    def test_tool_contracts_are_read_only(self) -> None:
        self.assertIn("search_knowledge", TOOL_REGISTRY)
        self.assertTrue(all(contract.read_only for contract in TOOL_REGISTRY.values()))
        ensure_read_only_tool("search_knowledge")
        with self.assertRaises(ValueError):
            ensure_read_only_tool("kubectl_delete_pod")

    def test_tool_response_normalization(self) -> None:
        response = ToolResponse(tool_name="get_recent_anomalies", status="ok", data={"anomalies": []}, evidence_refs=[], latency_ms=1.2)
        payload = response.model_dump()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["tool_name"], "get_recent_anomalies")

    def test_deterministic_planner_node_order(self) -> None:
        request = InvestigationRequest(trigger_type="anomaly", service="recommendationservice", objective="Investigate restart")
        plan = build_plan(request)
        self.assertEqual(plan[0], "supervisor")
        self.assertIn("anomaly_analyst", plan)
        self.assertEqual(plan[-1], "verifier_critic")

    def test_agent_state_serialization(self) -> None:
        state = AgentState(investigation_id="inv_test", trigger=InvestigationRequest(trigger_type="manual", service="cartservice"))
        state.knowledge_evidence.append({"chunk_id": "c1", "title": "Runbook"})
        dumped = state.model_dump()
        self.assertEqual(dumped["knowledge_evidence"][0]["chunk_id"], "c1")

    def test_report_includes_evidence_refs_and_text_only_remediation(self) -> None:
        request = InvestigationRequest(trigger_type="service", service="checkoutservice", objective="Investigate latency")
        state = AgentState(
            investigation_id="inv_report",
            trigger=request,
        )
        state.knowledge_evidence.append({"chunk_id": "chunk_1", "title": "Latency Runbook", "chunk_text": "Check upstream dependencies."})
        state.anomaly_refs.append({"anomaly_id": "anomaly_1", "severity": "high", "summary": "latency spike"})
        report = build_investigation_report(state)
        self.assertGreaterEqual(report["confidence"], 0.0)
        self.assertTrue(report["evidence"])
        self.assertTrue(any("SUGGESTION ONLY" in item for item in report["suggested_remediation"]))
        self.assertNotIn("executed", " ".join(report["suggested_remediation"]).lower())

    def test_verifier_low_confidence_without_evidence(self) -> None:
        request = InvestigationRequest(trigger_type="manual", objective="Investigate unknown issue")
        state = AgentState(investigation_id="inv_empty", trigger=request)
        report = build_investigation_report(state)
        self.assertLess(report["confidence"], 0.5)
        self.assertTrue(report["limitations"])

    def test_remediation_suggestions_are_text_only(self) -> None:
        suggestion = text_only_remediation(["kubectl rollout restart deployment checkoutservice"])
        self.assertIn("SUGGESTION ONLY", suggestion[0])
        self.assertIn("kubectl rollout restart", suggestion[0])

    def test_ids_and_lifecycle_event_are_stable_shape(self) -> None:
        first = stable_id("inv", "service:checkoutservice")
        second = stable_id("inv", "service:checkoutservice")
        self.assertEqual(first, second)
        state = AgentState(investigation_id=first, trigger=InvestigationRequest(trigger_type="service", service="checkoutservice"))
        event = build_lifecycle_event("investigation.completed", state, "completed")
        self.assertEqual(event["schema_version"], "phase6.v1")
        self.assertEqual(event["event_type"], "investigation.completed")
        self.assertEqual(event["investigation_id"], first)


if __name__ == "__main__":
    unittest.main()
