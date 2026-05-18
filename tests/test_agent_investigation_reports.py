from __future__ import annotations

import unittest

from services.shared.agents.reports import build_investigation_report
from services.shared.agents.safety import ensure_read_only_tool
from services.shared.agents.schemas import AgentState, InvestigationRequest
from services.shared.agents.tool_contracts import MUTATING_TOOL_NAMES, TOOL_REGISTRY


class InvestigationReportTests(unittest.TestCase):
    def test_audit_grade_report_fields_are_populated(self) -> None:
        state = AgentState(
            investigation_id="inv_audit",
            trigger=InvestigationRequest(trigger_type="service", service="orders", objective="Investigate errors"),
        )
        state.anomaly_refs.append({"anomaly_id": "anom_1", "service": "orders", "summary": "error rate spike"})
        state.telemetry_evidence.append({"event_id": "evt_1", "service": "orders", "health_status": "degraded"})
        state.blast_radius_evidence.append({
            "root_service": "orders",
            "blast_radius": {
                "root_service": "orders",
                "impact_path": ["orders", "payment"],
                "affected_services": ["orders", "payment"],
            },
        })
        state.causal_report_evidence.append({
            "incident": {
                "incident_id": "inc_1",
                "target_service": "orders",
                "causal_chain": ["orders", "payment"],
                "affected_services": ["payment"],
                "confidence": "medium",
            },
        })
        state.knowledge_evidence.append({
            "chunk_id": "chunk_1",
            "title": "Orders Runbook",
            "source_uri": "docs/runbooks/orders.md",
            "chunk_text": "Inspect upstream dependency health.",
        })

        report = build_investigation_report(state)

        for field in [
            "hypothesis",
            "supporting_evidence",
            "rejected_alternatives",
            "confidence_rationale",
            "causal_report_summary",
            "topology_blast_radius_summary",
            "knowledge_citations",
            "limitations",
            "recommended_next_action",
        ]:
            self.assertIn(field, report)
            self.assertTrue(report[field])
        self.assertGreaterEqual(report["confidence"], 0.5)
        self.assertIn("SUGGESTION ONLY", " ".join(report["suggested_remediation"]))

    def test_missing_evidence_forces_low_confidence(self) -> None:
        state = AgentState(
            investigation_id="inv_no_evidence",
            trigger=InvestigationRequest(trigger_type="manual", objective="Investigate unknown issue"),
        )

        report = build_investigation_report(state)

        self.assertLess(report["confidence"], 0.5)
        self.assertIn("no cited evidence", report["confidence_rationale"].lower())
        self.assertIn("No root-cause hypothesis", report["hypothesis"])
        self.assertIn("Collect anomaly", report["recommended_next_action"])

    def test_new_evidence_tools_are_registered_read_only(self) -> None:
        for tool_name in ["get_latest_blast_radius", "get_causal_report", "get_target_workload"]:
            self.assertIn(tool_name, TOOL_REGISTRY)
            self.assertTrue(TOOL_REGISTRY[tool_name].read_only)
            ensure_read_only_tool(tool_name)

    def test_no_mutating_tools_are_registered_for_agents(self) -> None:
        mutating_prefixes = ("apply_", "delete_", "patch_", "restart_", "scale_", "execute_", "approve_", "reject_")
        for tool_name, contract in TOOL_REGISTRY.items():
            self.assertNotIn(tool_name, MUTATING_TOOL_NAMES)
            self.assertFalse(tool_name.startswith(mutating_prefixes), tool_name)
            self.assertTrue(contract.read_only, tool_name)
            if contract.target_service in {"chaos-executor-service", "remediation-executor-service"}:
                self.assertEqual(contract.method, "GET", tool_name)


if __name__ == "__main__":
    unittest.main()
