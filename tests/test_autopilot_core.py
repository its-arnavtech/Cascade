from __future__ import annotations

import unittest

from services.shared.autopilot import AutopilotMode, AutopilotRunRequest, AutopilotWorkflow, InMemoryAutopilotRecorder


class FakeAutopilotClient:
    def __init__(self, *, approval: bool = False, execute_error: bool = False, dry_run_status: str = "passed") -> None:
        self.calls: list[str] = []
        self.approval = approval
        self.execute_error = execute_error
        self.dry_run_status = dry_run_status
        self.anomalies = [{"anomaly_id": "anom_1", "service": "catalogue", "namespace": "cascade-targets", "risk_score": 0.8}]

    async def detect_anomalies(self, service: str, namespace: str) -> dict:
        self.calls.append("detect")
        return {"status": "ok"}

    async def recent_anomalies(self, service: str, namespace: str, limit: int = 5) -> list[dict]:
        self.calls.append("recent_anomalies")
        return self.anomalies[:limit]

    async def anomaly_detail(self, anomaly_id: str) -> dict | None:
        self.calls.append("anomaly_detail")
        return {"anomaly_id": anomaly_id, "service": "catalogue", "namespace": "cascade-targets"}

    async def start_investigation(self, payload: dict) -> dict:
        self.calls.append("investigation")
        return {"investigation_id": "inv_1", "status": "completed", "summary": "catalogue had a reliability signal"}

    async def investigation_detail(self, investigation_id: str) -> dict:
        self.calls.append("investigation_detail")
        return {
            "run": {"investigation_id": investigation_id, "final_summary": "catalogue signal investigated"},
            "report": {"summary": "Likely catalogue degradation", "suspected_root_cause": "catalogue", "evidence": [{"type": "anomaly", "id": "anom_1"}], "recommended_next_steps": ["Review catalogue"], "suggested_remediation": ["SUGGESTION ONLY: investigate"]},
        }

    async def create_remediation_plan(self, payload: dict) -> dict:
        self.calls.append("plan")
        return {"plan_id": "rem_plan_1", "status": "ready", "plan": {"plan_id": "rem_plan_1", "action_type": payload.get("preferred_action_type", "investigate_only"), "post_checks": ["check"], "rollback_steps": ["rollback"]}}

    async def remediation_policy(self) -> dict:
        self.calls.append("policy")
        return {"execution_enabled": False, "live_demo_mode": False, "dangerous_actions_enabled": False, "real_remediation_enabled": False}

    async def dry_run_remediation(self, plan_id: str) -> dict:
        self.calls.append("dry_run")
        return {"execution": {"execution_id": "dry_1", "plan_id": plan_id, "dry_run": True, "validation_status": self.dry_run_status, "status": "completed"}}

    async def approval_status(self, plan_id: str) -> dict:
        self.calls.append("approval")
        if self.approval:
            return {"approved": True, "approval": {"approval_id": "approval_1", "plan_id": plan_id}}
        return {"approved": False, "approval": None}

    async def execute_remediation(self, plan_id: str, approval_id: str) -> dict:
        self.calls.append("execute")
        if self.execute_error:
            raise RuntimeError("backend safety still enforced")
        return {"execution": {"execution_id": "exec_1", "plan_id": plan_id, "executed": True, "status": "completed"}}

    async def recent_telemetry(self, service: str, namespace: str, limit: int = 50) -> list[dict]:
        self.calls.append("telemetry")
        return [{"event_id": "evt_1", "service": service, "namespace": namespace}]


class AutopilotCoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_run_reaches_recommendation_without_dry_run(self) -> None:
        client = FakeAutopilotClient()
        recorder = InMemoryAutopilotRecorder()
        run = await AutopilotWorkflow(client, recorder).run(AutopilotRunRequest(mode=AutopilotMode.READ_ONLY, service="catalogue"))

        self.assertEqual(run.status, "unchanged")
        self.assertEqual(run.final_result, "unchanged")
        self.assertEqual(run.remediation_plan_id, "rem_plan_1")
        self.assertNotIn("dry_run", client.calls)
        self.assertTrue(await recorder.get_steps(run.run_id))

    async def test_dry_run_executes_core_closed_loop_without_real_execution(self) -> None:
        client = FakeAutopilotClient()
        recorder = InMemoryAutopilotRecorder()
        run = await AutopilotWorkflow(client, recorder).run(AutopilotRunRequest(service="catalogue", preferred_action_type="investigate_only"))

        self.assertEqual(run.status, "unchanged")
        self.assertEqual(run.final_result, "unchanged")
        self.assertEqual(run.dry_run_execution_id, "dry_1")
        self.assertIn("dry_run", client.calls)
        self.assertNotIn("execute", client.calls)
        self.assertIn("before", run.verification)

    async def test_local_demo_execute_waits_for_missing_approval(self) -> None:
        client = FakeAutopilotClient(approval=False)
        run = await AutopilotWorkflow(client, InMemoryAutopilotRecorder()).run(AutopilotRunRequest(mode=AutopilotMode.LOCAL_DEMO_EXECUTE, service="catalogue", preferred_action_type="restart_deployment"))

        self.assertEqual(run.status, "waiting_for_approval")
        self.assertEqual(run.execution_id, "")
        self.assertIn("approval", client.calls)
        self.assertNotIn("execute", client.calls)

    async def test_service_failure_marks_run_failed(self) -> None:
        client = FakeAutopilotClient(approval=True, execute_error=True)
        run = await AutopilotWorkflow(client, InMemoryAutopilotRecorder()).run(AutopilotRunRequest(mode=AutopilotMode.LOCAL_DEMO_EXECUTE, service="catalogue", preferred_action_type="restart_deployment"))

        self.assertEqual(run.status, "failed")
        self.assertEqual(run.final_result, "failed")
        self.assertIn("backend safety still enforced", run.error_message)

    async def test_verification_maps_failed_dry_run_to_degraded(self) -> None:
        client = FakeAutopilotClient(dry_run_status="failed")
        run = await AutopilotWorkflow(client, InMemoryAutopilotRecorder()).run(AutopilotRunRequest(service="catalogue"))

        self.assertEqual(run.status, "degraded")
        self.assertEqual(run.final_result, "degraded")


if __name__ == "__main__":
    unittest.main()
