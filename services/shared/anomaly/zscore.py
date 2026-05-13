from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any

from services.shared.anomaly.models import ModelResult

FEATURES = ["event_count", "unhealthy_rate", "error_rate", "restart_rate", "avg_cpu", "max_cpu", "avg_memory", "max_memory", "avg_latency_ms", "max_latency_ms"]


def zscore_detect(window: dict[str, Any], history: list[dict[str, Any]], threshold: float = 3.0, min_history: int = 3) -> ModelResult:
    same_service = [row for row in history if row.get("service") == window.get("service") and row.get("window_id") != window.get("window_id")]
    if len(same_service) < min_history:
        return ModelResult("rolling_zscore", "statistical_baseline", False, 0.0, 0.0, f"insufficient_history: need {min_history}, found {len(same_service)}", {"history_count": len(same_service)})

    spikes = []
    max_abs_z = 0.0
    for feature in FEATURES:
        values = [_float(row.get(feature)) for row in same_service]
        mu = mean(values)
        sigma = pstdev(values)
        current = _float(window.get(feature))
        z = 0.0 if sigma == 0 else (current - mu) / sigma
        if math.isfinite(z):
            max_abs_z = max(max_abs_z, abs(z))
        if sigma > 0 and z >= threshold:
            spikes.append({"feature": feature, "current": current, "mean": mu, "std": sigma, "zscore": z})

    risk = min(1.0, max_abs_z / max(threshold * 1.5, 0.001))
    is_anomaly = bool(spikes)
    explanation = "; ".join(f"{s['feature']} z={s['zscore']:.2f} current={s['current']:.3f} mean={s['mean']:.3f} std={s['std']:.3f}" for s in spikes) if spikes else f"no rolling z-score exceeded {threshold}"
    return ModelResult("rolling_zscore", "statistical_baseline", is_anomaly, max_abs_z, risk if is_anomaly else 0.0, explanation, {"threshold": threshold, "spikes": spikes, "history_count": len(same_service)})


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0

