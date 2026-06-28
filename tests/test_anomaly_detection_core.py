from __future__ import annotations

import unittest
import asyncio
from datetime import UTC, datetime, timedelta

from services.shared.anomaly.ensemble import severity_for_risk
from services.shared.anomaly.isolation_forest import isolation_forest_detect
from services.shared.anomaly.thresholds import threshold_detect
from services.shared.anomaly.zscore import zscore_detect
from services.shared.features.extraction import extract_feature_windows
from services.shared.storage.clickhouse_client import ClickHouseClient


class RecordingClickHouseClient(ClickHouseClient):
    def __init__(self, existing_ids: set[str]) -> None:
        super().__init__()
        self.existing_ids = existing_ids
        self.inserted_rows: list[dict] = []

    async def existing_anomaly_ids(self, anomaly_ids: list[str]) -> set[str]:
        return self.existing_ids.intersection(anomaly_ids)

    async def insert_rows(self, table: str, rows):
        materialized = list(rows)
        self.inserted_rows.extend(materialized)
        return len(materialized)


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
        # A single sample of the cumulative restart counter shows no in-window
        # restart, so restart_rate must be 0 (the counter did not increase).
        self.assertEqual(first[0]["restart_rate"], 0.0)

    def test_restart_rate_uses_cumulative_counter_delta(self) -> None:
        # restart_count is the cumulative kube counter. A steady (already-restarted)
        # pod must NOT be flagged; only an in-window increase counts as a restart.
        steady = [
            {
                "observed_at": "2026-05-13 18:00:01.000",
                "service": "carts",
                "numeric_features_json": '{"restart_count":22}',
            }
            for _ in range(5)
        ]
        rows = extract_feature_windows(steady, 300)
        self.assertEqual(rows[0]["restart_rate"], 0.0)
        self.assertEqual(rows[0]["restart_signal_count"], 0)

        restarting = [
            {"observed_at": "2026-05-13 18:00:01.000", "service": "carts", "numeric_features_json": '{"restart_count":22}'},
            {"observed_at": "2026-05-13 18:02:01.000", "service": "carts", "numeric_features_json": '{"restart_count":24}'},
        ]
        rows = extract_feature_windows(restarting, 300)
        self.assertEqual(rows[0]["restart_signal_count"], 2)
        self.assertGreater(rows[0]["restart_rate"], 0.0)
        self.assertLessEqual(rows[0]["restart_rate"], 1.0)

    def test_feature_extraction_handles_missing_fields(self) -> None:
        rows = extract_feature_windows([{"observed_at": "2026-05-13 18:00:01.000"}], 300)
        self.assertEqual(rows[0]["service"], "unknown")
        self.assertEqual(rows[0]["avg_cpu"], 0.0)

    def test_error_rate_stays_within_unit_interval(self) -> None:
        # Each event is both error-status AND reports a positive RED error_rate;
        # it must be counted once, not twice (error_rate is a rate in [0, 1]).
        events = [
            {
                "observed_at": "2026-05-13 18:00:01.000",
                "service": "carts",
                "health_status": "error",
                "numeric_features_json": '{"error_rate":0.1}',
            }
            for _ in range(4)
        ]
        rows = extract_feature_windows(events, 300)
        self.assertEqual(rows[0]["event_count"], 4)
        self.assertLessEqual(rows[0]["error_count"], rows[0]["event_count"])
        self.assertLessEqual(rows[0]["error_rate"], 1.0)
        self.assertGreater(rows[0]["error_rate"], 0.0)

    def test_threshold_detector_flags_rates(self) -> None:
        result = threshold_detect({"unhealthy_rate": 0.9, "error_rate": 0.6, "restart_rate": 0.7, "latency_p95_ms": 900.0, "availability_rate": 0.95, "event_count": 20})
        self.assertTrue(result.is_anomaly)
        self.assertGreaterEqual(result.risk_score, 0.85)
        self.assertIn("latency_p95_ms", result.explanation)
        self.assertIn("availability_rate", result.explanation)

    def test_threshold_detector_normal_for_healthy_window(self) -> None:
        result = threshold_detect({"unhealthy_rate": 0.0, "error_rate": 0.0, "restart_rate": 0.0, "event_count": 2})
        self.assertFalse(result.is_anomaly)

    def test_zscore_handles_zero_std(self) -> None:
        start = datetime(2026, 5, 20, tzinfo=UTC)
        history = [{"service": "carts", "window_id": f"w{i}", "event_count": 5, "window_start": (start + timedelta(minutes=i)).isoformat()} for i in range(4)]
        result = zscore_detect({"service": "carts", "window_id": "current", "event_count": 5, "window_start": (start + timedelta(minutes=10)).isoformat()}, history)
        self.assertFalse(result.is_anomaly)

    def test_zscore_detects_spike(self) -> None:
        start = datetime(2026, 5, 20, tzinfo=UTC)
        history = [{"service": "carts", "window_id": f"w{i}", "event_count": 5 + i, "window_start": (start + timedelta(minutes=i)).isoformat()} for i in range(5)]
        result = zscore_detect({"service": "carts", "window_id": "current", "event_count": 50, "window_start": (start + timedelta(minutes=10)).isoformat()}, history, threshold=2.0)
        self.assertTrue(result.is_anomaly)

    def test_zscore_reports_insufficient_same_service_history(self) -> None:
        start = datetime(2026, 5, 20, tzinfo=UTC)
        history = [{"service": "other", "window_id": "w1", "event_count": 5, "window_start": start.isoformat()}]
        result = zscore_detect({"service": "carts", "window_id": "current", "event_count": 50, "window_start": (start + timedelta(minutes=10)).isoformat()}, history)

        self.assertFalse(result.is_anomaly)
        self.assertEqual(result.evidence["status"], "insufficient_data")
        self.assertIn("insufficient_data", result.explanation)

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

    def test_anomaly_insert_skips_existing_stable_ids(self) -> None:
        client = RecordingClickHouseClient({"anomaly-a"})
        inserted = asyncio.run(client.insert_anomaly_events([
            {"anomaly_id": "anomaly-a", "service": "catalogue"},
            {"anomaly_id": "anomaly-b", "service": "catalogue"},
            {"anomaly_id": "anomaly-b", "service": "catalogue"},
        ]))

        self.assertEqual(inserted, 1)
        self.assertEqual(client.inserted_rows, [{"anomaly_id": "anomaly-b", "service": "catalogue"}])


if __name__ == "__main__":
    unittest.main()
