from __future__ import annotations

import math
import unittest
from datetime import UTC, datetime, timedelta

from services.shared.causality.engine import align_lagged_series, analyze_causality, extract_service_feature_series, normalize_feature_windows
from services.shared.features.extraction import ch_datetime


def window(service: str, index: int, value: float, start: datetime) -> dict[str, object]:
    window_start = start + timedelta(minutes=5 * index)
    return {
        "window_id": f"{service}-{index}",
        "service": service,
        "namespace": "cascade-system",
        "workload": service,
        "window_start": ch_datetime(window_start),
        "window_end": ch_datetime(window_start + timedelta(minutes=5)),
        "error_rate": value,
        "avg_latency_ms": value * 100.0,
        "feature_vector_json": "{}",
    }


class CausalityCoreTests(unittest.TestCase):
    def test_lagged_alignment_uses_source_before_target(self) -> None:
        start = datetime(2026, 5, 18, tzinfo=UTC)
        rows = [window("source", i, float(i), start) for i in range(5)]
        rows += [window("target", i, float(i * 10), start) for i in range(5)]
        normalized = normalize_feature_windows(rows)
        normalized_source = extract_service_feature_series(normalized, "source", "error_rate")
        normalized_target = extract_service_feature_series(normalized, "target", "error_rate")
        x_values, y_values = align_lagged_series(normalized_source, normalized_target, 2)
        self.assertEqual(x_values, [0.0, 1.0, 2.0])
        self.assertEqual(y_values, [20.0, 30.0, 40.0])

    def test_synthetic_leading_service_ranks_first(self) -> None:
        start = datetime(2026, 5, 18, tzinfo=UTC)
        source = [0.2 + math.sin(i / 3.0) for i in range(48)]
        target = [0.0, 0.0] + source[:-2]
        unrelated = [math.cos(i * 1.7) for i in range(48)]
        rows = []
        for index, value in enumerate(source):
            rows.append(window("orders", index, value, start))
        for index, value in enumerate(target):
            rows.append(window("front-end", index, value, start))
        for index, value in enumerate(unrelated):
            rows.append(window("payment", index, value, start))

        report = analyze_causality(
            rows,
            [{"service": "orders", "severity": "high", "risk_score": 0.8, "anomaly_id": "a1"}],
            {"dependencies": {"orders": ["front-end"], "payment": ["front-end"]}},
            target_service="front-end",
            target_feature="error_rate",
            max_lag_windows=4,
            min_correlation_samples=12,
            min_granger_samples=30,
        )

        self.assertEqual(report["status"], "ranked")
        self.assertEqual(report["candidates"][0]["source_service"], "orders")
        self.assertEqual(report["candidates"][0]["lag_windows"], 2)
        self.assertLess(report["candidates"][0]["best_p_value"], 0.001)
        self.assertTrue(report["candidates"][0]["granger"]["tested"])
        self.assertIn("statistical precursor", report["summary"])
        self.assertIn("ranked evidence", report["summary"])

    def test_insufficient_samples_does_not_emit_p_values_or_claim(self) -> None:
        start = datetime(2026, 5, 18, tzinfo=UTC)
        rows = []
        for index in range(4):
            rows.append(window("source", index, float(index), start))
            rows.append(window("target", index, float(index), start))

        report = analyze_causality(
            rows,
            [],
            None,
            target_service="target",
            target_feature="error_rate",
            max_lag_windows=2,
            min_correlation_samples=8,
            min_granger_samples=30,
        )

        self.assertEqual(report["status"], "insufficient_samples")
        self.assertIn("Insufficient evidence", report["summary"])
        self.assertIsNone(report["candidates"][0]["best_p_value"])
        self.assertFalse(report["candidates"][0]["granger"]["tested"])
        self.assertIn("insufficient_samples", report["candidates"][0]["pearson"]["reason"])


if __name__ == "__main__":
    unittest.main()
