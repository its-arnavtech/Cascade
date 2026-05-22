from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

from services.shared.chaos.schemas import ChaosCampaignRequest, ChaosCampaignStartRequest


MODULE_PATH = Path(__file__).resolve().parents[1] / "services" / "chaos-planner-service" / "app" / "main.py"
spec = importlib.util.spec_from_file_location("chaos_planner_campaigns_main", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["chaos_planner_campaigns_main"] = module
spec.loader.exec_module(module)


class ChaosCampaignTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        async def noop(*args, **kwargs):
            return None

        async def evidence(service: str, namespace: str):
            return {"service": service, "namespace": namespace, "telemetry_events": 3, "anomalies": 0, "latest_rca": {"status": "ok"}}

        self.originals = {
            "_insert_plan": module._insert_plan,
            "_audit": module._audit,
            "_insert_campaign_step": module._insert_campaign_step,
            "_campaign_evidence": module._campaign_evidence,
            "_execute_campaign_plan": module._execute_campaign_plan,
        }
        module._insert_plan = noop
        module._audit = noop
        module._insert_campaign_step = noop
        module._campaign_evidence = evidence

    async def asyncTearDown(self) -> None:
        for name, value in self.originals.items():
            setattr(module, name, value)

    def _campaign(self, **overrides):
        data = {
            "name": "Core campaign",
            "allowed_services": ["catalogue", "carts"],
            "experiment_templates": [
                {"name": "kill catalogue", "experiment_kind": "pod_kill", "target_service": "catalogue", "duration_seconds": 10},
                {"name": "delay carts", "experiment_kind": "network_delay", "target_service": "carts", "duration_seconds": 10},
            ],
            "max_experiments_per_run": 2,
        }
        data.update(overrides)
        request = ChaosCampaignRequest(
            **data,
        )
        return module._campaign_dict(request)

    async def test_dry_run_campaign_step_completes_without_real_execution(self) -> None:
        async def execute(plan_id: str, payload: ChaosCampaignStartRequest, dry_run: bool):
            return {"run_id": "chaos_run_dry", "status": "dry_run", "dry_run": dry_run, "cleanup_status": "not_required"}

        module._execute_campaign_plan = execute
        campaign = self._campaign()
        run = module._campaign_run_dict("campaign_run_1", campaign, ChaosCampaignStartRequest(dry_run=True), "running", True, [], "")

        step = await module._run_campaign_template(campaign, run, ChaosCampaignStartRequest(dry_run=True), campaign["experiment_templates"][0], 1, True)

        self.assertEqual(step["status"], "completed")
        self.assertEqual(step["chaos_run_id"], "chaos_run_dry")
        self.assertEqual(step["cleanup_status"], "not_required")

    async def test_campaign_blocks_unsafe_target(self) -> None:
        async def execute(plan_id: str, payload: ChaosCampaignStartRequest, dry_run: bool):
            raise AssertionError("blocked campaign step must not execute")

        module._execute_campaign_plan = execute
        campaign = self._campaign(allowed_services=["catalogue"])
        template = {"name": "blocked", "experiment_kind": "pod_kill", "target_service": "front-end", "duration_seconds": 10}
        run = module._campaign_run_dict("campaign_run_2", campaign, ChaosCampaignStartRequest(dry_run=True), "running", True, [], "")

        step = await module._run_campaign_template(campaign, run, ChaosCampaignStartRequest(dry_run=True), template, 1, True)

        self.assertEqual(step["status"], "blocked")
        self.assertIn("protected", step["blocked_reason"])

    async def test_allowed_local_demo_campaign_delegates_cleanup_to_executor(self) -> None:
        async def execute(plan_id: str, payload: ChaosCampaignStartRequest, dry_run: bool):
            return {"run_id": "chaos_run_live", "status": "completed", "dry_run": dry_run, "cleanup_status": "cleaned_up"}

        module._execute_campaign_plan = execute
        campaign = self._campaign(dry_run=False, local_demo_execution_enabled=True)
        run = module._campaign_run_dict("campaign_run_3", campaign, ChaosCampaignStartRequest(dry_run=False, approved=True), "running", False, [], "")

        step = await module._run_campaign_template(campaign, run, ChaosCampaignStartRequest(dry_run=False, approved=True), campaign["experiment_templates"][0], 1, False)

        self.assertEqual(step["status"], "completed")
        self.assertEqual(step["cleanup_status"], "cleaned_up")

    async def test_campaign_failure_records_cleanup_delegated(self) -> None:
        async def execute(plan_id: str, payload: ChaosCampaignStartRequest, dry_run: bool):
            raise RuntimeError("executor unavailable")

        module._execute_campaign_plan = execute
        campaign = self._campaign()
        run = module._campaign_run_dict("campaign_run_4", campaign, ChaosCampaignStartRequest(dry_run=True), "running", True, [], "")

        step = await module._run_campaign_template(campaign, run, ChaosCampaignStartRequest(dry_run=True), campaign["experiment_templates"][0], 1, True)

        self.assertEqual(step["status"], "failed")
        self.assertEqual(step["cleanup_status"], "cleanup_delegated_to_executor")

    def test_campaign_report_summarizes_blocked_and_recommendations(self) -> None:
        campaign = self._campaign()
        report = module._campaign_report(
            campaign,
            [
                {"status": "completed", "target_service": "catalogue", "evidence_after": {"latest_rca": {"explanation": "ok"}}},
                {"status": "blocked", "target_service": "front-end", "blocked_reason": "protected"},
            ],
            "completed_with_blocks",
            "",
        )

        self.assertEqual(report["experiments_run"], 1)
        self.assertEqual(report["skipped_or_blocked"][0]["reason"], "protected")
        self.assertTrue(report["recommendations_created"])


if __name__ == "__main__":
    unittest.main()
