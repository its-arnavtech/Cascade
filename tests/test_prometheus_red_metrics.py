from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

import httpx

OBSERVATION_PATH = Path(__file__).resolve().parents[1] / "services" / "observation-service"
sys.path.insert(0, str(OBSERVATION_PATH))

from app.normalizer import normalize_snapshot  # noqa: E402
from app.prometheus_client import PrometheusClient, PrometheusError  # noqa: E402

sys.path.remove(str(OBSERVATION_PATH))
for module_name in list(sys.modules):
    if module_name == "app" or module_name.startswith("app."):
        del sys.modules[module_name]


def vector_payload(metric: dict[str, str], value: str = "1") -> dict:
    return {"status": "success", "data": {"resultType": "vector", "result": [{"metric": metric, "value": [1, value]}]}}


class PrometheusRedMetricsTests(unittest.TestCase):
    def test_query_with_status_success(self) -> None:
        transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=vector_payload({"service": "frontend"}, "7")))
        result = asyncio.run(PrometheusClient("http://prometheus", transport=transport).query_with_status("request_rate", "up"))

        self.assertEqual(result.status.status, "success")
        self.assertEqual(result.status.result_count, 1)
        self.assertIsNotNone(result.payload)

    def test_query_with_status_empty(self) -> None:
        transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"status": "success", "data": {"resultType": "vector", "result": []}}))
        result = asyncio.run(PrometheusClient("http://prometheus", transport=transport).query_with_status("latency_p95_ms", "absent"))

        self.assertEqual(result.status.status, "empty")
        self.assertIn("no samples", result.status.warning or "")
        self.assertEqual(result.status.result_count, 0)

    def test_query_malformed_response_raises(self) -> None:
        transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=b"not-json"))

        with self.assertRaises(PrometheusError):
            asyncio.run(PrometheusClient("http://prometheus", transport=transport).query("up"))

    def test_query_with_status_failed(self) -> None:
        transport = httpx.MockTransport(lambda _request: httpx.Response(503, json={"status": "error"}))
        result = asyncio.run(PrometheusClient("http://prometheus", transport=transport).query_with_status("request_rate", "up"))

        self.assertEqual(result.status.status, "failed")
        self.assertIsNone(result.payload)
        self.assertIn("Prometheus returned HTTP", result.status.error or "")

    def test_normalize_snapshot_marks_missing_red_metrics(self) -> None:
        query_status = {
            "cpu": {"status": "success", "result_count": 1},
            "request_rate": {"status": "empty", "warning": "no samples"},
            "error_rate": {"status": "failed", "error": "bad query"},
            "latency_p50_ms": {"status": "empty", "warning": "no samples"},
            "latency_p95_ms": {"status": "empty", "warning": "no samples"},
            "latency_p99_ms": {"status": "empty", "warning": "no samples"},
        }
        snapshot = normalize_snapshot(
            "cascade-targets",
            {"cpu": vector_payload({"namespace": "cascade-targets", "pod": "frontend-abc12345-x1y2z"}, "0.1")},
            query_status=query_status,
        )

        self.assertEqual(snapshot.pods[0].evidence_quality, "insufficient_data")
        self.assertIn("request_rate", snapshot.pods[0].missing_metrics)
        self.assertEqual(snapshot.pods[0].metric_status["error_rate"], "failed")
        self.assertTrue(snapshot.collection_warnings)


if __name__ == "__main__":
    unittest.main()
