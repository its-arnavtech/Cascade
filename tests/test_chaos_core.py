from __future__ import annotations

import unittest
import asyncio
from pathlib import Path

from services.shared.chaos.events import chaos_event
from services.shared.chaos.safety import default_policy, validate_plan
from services.shared.chaos.scoring import compute_resilience_score, grade_for_score
from services.shared.chaos.templates import build_manifest, stable_id
from services.shared.storage.clickhouse_client import ClickHouseClient


class RecordingClickHouseClient(ClickHouseClient):
    def __init__(self) -> None:
        super().__init__()
        self.queries: list[str] = []

    async def fetch_json_rows(self, query: str):
        self.queries.append(query)
        return []


class Phase7CoreTests(unittest.TestCase):
    def _plan(self, namespace: str = "cascade-targets", service: str = "catalogue", kind: str = "pod_kill", duration: int = 30) -> dict:
        experiment_id = stable_id("chaos_exp", f"{namespace}:{service}:{kind}")
        manifest = build_manifest(kind, experiment_id, namespace, service, duration)
        return {
            "plan_id": "plan_test",
            "experiment_id": experiment_id,
            "experiment_kind": kind,
            "target_namespace": namespace,
            "target_service": service,
            "target_selector": manifest["spec"]["selector"],
            "duration_seconds": duration,
            "manifest": manifest,
            "blast_radius_score": 0.2,
        }

    def test_safety_rejects_denied_namespace(self) -> None:
        result = validate_plan(self._plan(namespace="kube-system"), default_policy())
        self.assertFalse(result.allowed)
        self.assertTrue(any("denied" in item for item in result.violations))

    def test_safety_rejects_broad_selector(self) -> None:
        plan = self._plan()
        plan["target_selector"] = {"namespaces": ["cascade-targets"], "labelSelectors": {}}
        plan["manifest"]["spec"]["selector"] = plan["target_selector"]
        result = validate_plan(plan, default_policy())
        self.assertFalse(result.allowed)
        self.assertTrue(any("selector" in item for item in result.violations))

    def test_safety_requires_approval_for_real_execution(self) -> None:
        result = validate_plan(self._plan(), default_policy(), approved=False, dry_run=False)
        self.assertFalse(result.allowed)
        self.assertTrue(any("approved" in item for item in result.violations))

    def test_safety_allows_bounded_pod_kill(self) -> None:
        result = validate_plan(self._plan(), default_policy(), approved=True, dry_run=False)
        self.assertTrue(result.allowed)
        self.assertGreaterEqual(result.safety_score, 0.9)

    def test_pod_kill_template_has_required_labels(self) -> None:
        manifest = build_manifest("pod_kill", "chaos_exp_test", "cascade-targets", "catalogue", 30)
        self.assertEqual(manifest["kind"], "PodChaos")
        self.assertEqual(manifest["metadata"]["namespace"], "cascade-targets")
        self.assertEqual(manifest["metadata"]["labels"]["cascade.io/phase"], "phase7")
        self.assertEqual(manifest["spec"]["mode"], "one")

    def test_grade_mapping(self) -> None:
        self.assertEqual(grade_for_score(0.95), "A")
        self.assertEqual(grade_for_score(0.76), "B")
        self.assertEqual(grade_for_score(0.61), "C")
        self.assertEqual(grade_for_score(0.41), "D")
        self.assertEqual(grade_for_score(0.2), "F")

    def test_scoring_penalizes_anomalies_and_incidents(self) -> None:
        plan = {"blast_radius_score": 0.2, "target_service": "catalogue"}
        clean = compute_resilience_score({"cleanup_status": "cleaned_up"}, {"telemetry_events_count": 5, "anomaly_events_count": 0, "incidents_count": 0, "affected_services": ["catalogue"]}, plan)
        noisy = compute_resilience_score({"cleanup_status": "cleaned_up"}, {"telemetry_events_count": 5, "anomaly_events_count": 4, "incidents_count": 2, "affected_services": ["catalogue", "front-end"]}, plan)
        self.assertGreater(clean["resilience_score"], noisy["resilience_score"])

    def test_event_schema_builder_is_compact(self) -> None:
        event = chaos_event("chaos.run.started", self._plan(), {"run_id": "run1", "status": "running", "dry_run": False, "approved": True}, None, "started")
        self.assertEqual(event["schema_version"], "phase7.v1")
        self.assertEqual(event["event_type"], "chaos.run.started")
        self.assertEqual(event["run_id"], "run1")

    def test_rbac_manifest_has_no_cluster_admin(self) -> None:
        text = Path("infra/kubernetes/chaos-executor-service/rbac.yaml").read_text(encoding="utf-8")
        self.assertNotIn("cluster-admin", text)
        self.assertNotIn("deployments", text)
        self.assertIn("podchaos", text)

    def test_chaos_run_queries_select_latest_canonical_state(self) -> None:
        client = RecordingClickHouseClient()
        asyncio.run(client.recent_chaos_runs(limit=7, service="catalogue", status="completed"))
        asyncio.run(client.chaos_run_detail("chaos_run_1"))

        recent_query = client.queries[0]
        detail_query = client.queries[1]
        self.assertIn("row_number() OVER", recent_query)
        self.assertIn("PARTITION BY run_id", recent_query)
        self.assertIn("target_service = 'catalogue'", recent_query)
        self.assertIn("status = 'completed'", recent_query)
        self.assertIn("LIMIT 7", recent_query)
        self.assertIn("run_id = 'chaos_run_1'", detail_query)


if __name__ == "__main__":
    unittest.main()
