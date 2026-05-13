from __future__ import annotations

from typing import Any

from services.shared.anomaly.models import ModelResult


def threshold_detect(
    window: dict[str, Any],
    unhealthy_threshold: float = 0.5,
    error_threshold: float = 0.2,
    restart_threshold: float = 0.1,
    event_count_threshold: int = 100,
) -> ModelResult:
    unhealthy = float(window.get("unhealthy_rate") or 0.0)
    error = float(window.get("error_rate") or 0.0)
    restart = float(window.get("restart_rate") or 0.0)
    event_count = int(window.get("event_count") or 0)
    reasons = []
    risk = 0.0
    for name, value, threshold, weight in [
        ("unhealthy_rate", unhealthy, unhealthy_threshold, 0.85),
        ("error_rate", error, error_threshold, 0.75),
        ("restart_rate", restart, restart_threshold, 0.65),
    ]:
        if value >= threshold:
            reasons.append(f"{name} {value:.3f} >= {threshold:.3f}")
            risk = max(risk, min(1.0, weight * (value / max(threshold, 0.001))))
    if event_count >= event_count_threshold:
        reasons.append(f"event_count {event_count} >= {event_count_threshold}")
        risk = max(risk, 0.4)
    is_anomaly = bool(reasons)
    explanation = "; ".join(reasons) if reasons else "threshold detector found rates within configured limits"
    return ModelResult("threshold", "rule_baseline", is_anomaly, risk, min(risk, 1.0), explanation, {
        "unhealthy_rate": unhealthy,
        "error_rate": error,
        "restart_rate": restart,
        "event_count": event_count,
        "thresholds": {
            "unhealthy_rate": unhealthy_threshold,
            "error_rate": error_threshold,
            "restart_rate": restart_threshold,
            "event_count": event_count_threshold,
        },
    })

