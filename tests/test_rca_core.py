from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from services.shared.features.extraction import ch_datetime
from services.shared.rca import build_rca_report


def window(service: str, index: int, start: datetime, **values: object) -> dict[str, object]:
    window_start = start + timedelta(minutes=5 * index)
    return {
        "window_id": f"{service}-{index}",
        "service": service,
        "namespace": "cascade-targets",
        "workload": service,
        "window_start": ch_datetime(window_start),
        "window_end": ch_datetime(window_start + timedelta(minutes=5)),
        "feature_vector_json": "{}",
        **values,
    }


class RcaCoreTests(unittest.TestCase):
    def test_dependency_latency_first_ranks_root_cause(self) -> None:
        start = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
        rows = [
            window("paymentservice", 0, start, latency_p95_ms=1250.0, error_rate=0.0, availability_rate=1.0, readiness_rate=1.0),
            window("checkoutservice", 1, start, latency_p95_ms=400.0, error_rate=0.22, availability_rate=0.98, readiness_rate=1.0),
            window("frontend", 2, start, latency_p95_ms=450.0, error_rate=0.18, availability_rate=0.97, readiness_rate=1.0),
        ]
        anomalies = [
            {"anomaly_id": "a-payment", "service": "paymentservice", "detected_at": ch_datetime(start), "risk_score": 0.8, "explanation": "latency_p95_ms 1250 > 750"},
            {"anomaly_id": "a-checkout", "service": "checkoutservice", "detected_at": ch_datetime(start + timedelta(minutes=5)), "risk_score": 0.65, "explanation": "error_rate 0.22 >= 0.20"},
            {"anomaly_id": "a-front", "service": "frontend", "detected_at": ch_datetime(start + timedelta(minutes=10)), "risk_score": 0.55, "explanation": "availability_rate 0.97 < 0.99"},
        ]
        topology = {"dependencies": {"frontend": ["checkoutservice"], "checkoutservice": ["paymentservice"], "paymentservice": []}}
        experiments = [{"experiment_id": "chaos-payment", "target_service": "paymentservice", "started_at": ch_datetime(start - timedelta(minutes=1)), "status": "completed"}]

        report = build_rca_report(rows, anomalies, topology, experiments, target_service="frontend")

        self.assertEqual(report["status"], "ranked")
        self.assertEqual(report["likely_root_cause_service"], "paymentservice")
        self.assertIn("checkoutservice", report["affected_downstream_services"])
        self.assertIn("frontend", report["affected_downstream_services"])
        self.assertEqual(report["related_chaos_experiment"]["experiment_id"], "chaos-payment")
        self.assertGreaterEqual(report["confidence_score"], 0.5)
        self.assertIn("paymentservice", report["explanation"])

    def test_insufficient_data_report_does_not_claim_root_cause(self) -> None:
        report = build_rca_report([], [], None, [], target_service=None)

        self.assertEqual(report["status"], "insufficient_data")
        self.assertEqual(report["confidence_score"], 0.1)
        self.assertFalse(report["likely_root_cause_service"])
        self.assertIn("No target service", report["explanation"])

    def test_missing_red_and_request_direction_caps_confidence(self) -> None:
        start = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
        rows = [
            window("paymentservice", 0, start, missing_metric_count=5, warning_event_count=1.0),
            window("frontend", 1, start, missing_metric_count=5, warning_event_count=1.0),
        ]
        anomalies = [
            {"anomaly_id": "a-payment", "service": "paymentservice", "detected_at": ch_datetime(start), "risk_score": 0.9, "explanation": "insufficient_data"},
            {"anomaly_id": "a-front", "service": "frontend", "detected_at": ch_datetime(start + timedelta(minutes=5)), "risk_score": 0.8, "explanation": "insufficient_data"},
        ]
        topology = {"dependencies": {"frontend": ["paymentservice"], "paymentservice": []}}

        report = build_rca_report(rows, anomalies, topology, [], target_service="frontend")

        self.assertLessEqual(report["confidence_score"], 0.45)
        self.assertTrue(any("RED metrics" in item for item in report["limitations"]))
        self.assertTrue(any("request-direction" in item for item in report["limitations"]))

    def test_traffic_edge_evidence_avoids_request_direction_limitation(self) -> None:
        start = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
        rows = [
            window("paymentservice", 0, start, latency_p95_ms=1250.0, error_rate=0.0),
            window("frontend", 1, start, error_rate=0.2),
        ]
        anomalies = [{"anomaly_id": "a-payment", "service": "paymentservice", "detected_at": ch_datetime(start), "risk_score": 0.9, "explanation": "latency_p95_ms high"}]
        topology = {
            "dependencies": {"frontend": ["paymentservice"], "paymentservice": []},
            "edges": [
                {
                    "source": "frontend",
                    "target": "paymentservice",
                    "relation": "depends_on",
                    "source_type": "traffic_inferred",
                    "confidence": 0.8,
                    "evidence": "traffic inferred frontend -> paymentservice",
                }
            ],
        }

        report = build_rca_report(rows, anomalies, topology, [], target_service="frontend")

        self.assertFalse(any("request-direction" in item for item in report["limitations"]))
        self.assertTrue(any(item.get("source_type") == "traffic_inferred" for item in report["evidence"]))


if __name__ == "__main__":
    unittest.main()
