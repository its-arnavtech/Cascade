from __future__ import annotations

import unittest
from datetime import UTC, datetime

from services.shared.anomaly.ensemble import severity_for_risk
from services.shared.anomaly.isolation_forest import isolation_forest_detect
from services.shared.anomaly.thresholds import threshold_detect
from services.shared.anomaly.zscore import zscore_detect
from services.shared.features.extraction import extract_feature_windows


class Phase4CoreTests(unittest.TestCase):
    def test_feature_window_grouping_is_deterministic(self) -> None:
        event = {
            "event_id": "e1",
            "observed_at": "2026-05-13 18:00:01.000",
            "service": "carts",
            "namespace": "cascade-targets",
            "workload": "carts",
            "health_status": "warning",
            "numeric_features_json": '{"cpu_percent":10,"memory_mib":50,"restart_count":1}',
        }
        first = extract_feature_windows([event], 300, datetime(2026, 5, 13, tzinfo=UTC))
        second = extract_feature_windows([event], 300, datetime(2026, 5, 13, tzinfo=UTC))
        self.assertEqual(first[0]["window_id"], second[0]["window_id"])
        self.assertEqual(first[0]["restart_rate"], 1.0)

    def test_feature_extraction_handles_missing_fields(self) -> None:
        rows = extract_feature_windows([{"observed_at": "2026-05-13 18:00:01.000"}], 300)
        self.assertEqual(rows[0]["service"], "unknown")
        self.assertEqual(rows[0]["avg_cpu"], 0.0)

    def test_threshold_detector_flags_rates(self) -> None:
        result = threshold_detect({"unhealthy_rate": 0.9, "error_rate": 0.6, "restart_rate": 0.7, "event_count": 20})
        self.assertTrue(result.is_anomaly)
        self.assertGreaterEqual(result.risk_score, 0.85)

    def test_threshold_detector_normal_for_healthy_window(self) -> None:
        result = threshold_detect({"unhealthy_rate": 0.0, "error_rate": 0.0, "restart_rate": 0.0, "event_count": 2})
        self.assertFalse(result.is_anomaly)

    def test_zscore_handles_zero_std(self) -> None:
        history = [{"service": "carts", "window_id": f"w{i}", "event_count": 5} for i in range(4)]
        result = zscore_detect({"service": "carts", "window_id": "current", "event_count": 5}, history)
        self.assertFalse(result.is_anomaly)

    def test_zscore_detects_spike(self) -> None:
        history = [{"service": "carts", "window_id": f"w{i}", "event_count": 5 + i} for i in range(5)]
        result = zscore_detect({"service": "carts", "window_id": "current", "event_count": 50}, history, threshold=2.0)
        self.assertTrue(result.is_anomaly)

    def test_isolation_forest_handles_insufficient_history(self) -> None:
        result = isolation_forest_detect({"window_id": "current"}, [], min_windows=20)
        self.assertFalse(result.is_anomaly)
        self.assertIn("insufficient_history", result.explanation.lower() or result.explanation)

    def test_severity_mapping(self) -> None:
        self.assertEqual(severity_for_risk(0.9), "critical")
        self.assertEqual(severity_for_risk(0.7), "high")
        self.assertEqual(severity_for_risk(0.5), "medium")
        self.assertEqual(severity_for_risk(0.3), "low")
        self.assertEqual(severity_for_risk(0.1), "normal")


if __name__ == "__main__":
    unittest.main()
