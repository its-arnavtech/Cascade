from __future__ import annotations

from typing import Any

from services.shared.anomaly.models import ModelResult


def threshold_detect(
    window: dict[str, Any],
    unhealthy_threshold: float = 0.5,
    error_threshold: float = 0.2,
    restart_threshold: float = 0.1,
    event_count_threshold: int = 100,
    latency_p95_threshold_ms: float = 750.0,
    latency_p99_threshold_ms: float = 1500.0,
    cpu_threshold: float = 80.0,
    memory_threshold_mib: float = 1024.0,
    availability_threshold: float = 0.99,
    readiness_threshold: float = 0.99,
    warning_event_threshold: float = 0.0,
) -> ModelResult:
    unhealthy = float(window.get("unhealthy_rate") or 0.0)
    error = float(window.get("error_rate") or 0.0)
    restart = float(window.get("restart_rate") or 0.0)
    latency_p95 = float(window.get("latency_p95_ms") or window.get("max_latency_ms") or 0.0)
    latency_p99 = float(window.get("latency_p99_ms") or window.get("max_latency_ms") or 0.0)
    max_cpu = float(window.get("max_cpu") or 0.0)
    max_memory = float(window.get("max_memory") or 0.0)
    availability = float(window.get("availability_rate") or 0.0)
    readiness = float(window.get("readiness_rate") or 0.0)
    warning_events = float(window.get("warning_event_count") or 0.0)
    missing_metric_count = int(window.get("missing_metric_count") or 0)
    dependency_unhealthy_count = int(window.get("dependency_unhealthy_count") or 0)
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
    for name, value, threshold, weight in [
        ("latency_p95_ms", latency_p95, latency_p95_threshold_ms, 0.72),
        ("latency_p99_ms", latency_p99, latency_p99_threshold_ms, 0.78),
        ("max_cpu", max_cpu, cpu_threshold, 0.60),
        ("max_memory", max_memory, memory_threshold_mib, 0.55),
        ("warning_event_count", warning_events, warning_event_threshold, 0.55),
    ]:
        if value > threshold:
            reasons.append(f"{name} {value:.3f} > {threshold:.3f}")
            risk = max(risk, min(1.0, weight * (value / max(threshold, 0.001))))
    if availability > 0 and availability < availability_threshold:
        reasons.append(f"availability_rate {availability:.3f} < {availability_threshold:.3f}")
        risk = max(risk, 0.7)
    if readiness > 0 and readiness < readiness_threshold:
        reasons.append(f"readiness_rate {readiness:.3f} < {readiness_threshold:.3f}")
        risk = max(risk, 0.65)
    if dependency_unhealthy_count > 0:
        reasons.append(f"dependency_unhealthy_count {dependency_unhealthy_count} > 0")
        risk = max(risk, 0.5)
    if event_count >= event_count_threshold:
        reasons.append(f"event_count {event_count} >= {event_count_threshold}")
        risk = max(risk, 0.4)
    is_anomaly = bool(reasons)
    insufficient = missing_metric_count > 0
    if insufficient:
        reasons.append(f"insufficient_data: {missing_metric_count} metric sample(s) missing")
    explanation = "; ".join(reasons) if reasons else "threshold detector found rates within configured limits"
    return ModelResult("threshold", "rule_baseline", is_anomaly, risk, min(risk, 1.0), explanation, {
        "unhealthy_rate": unhealthy,
        "error_rate": error,
        "restart_rate": restart,
        "event_count": event_count,
        "latency_p95_ms": latency_p95,
        "latency_p99_ms": latency_p99,
        "max_cpu": max_cpu,
        "max_memory": max_memory,
        "availability_rate": availability,
        "readiness_rate": readiness,
        "warning_event_count": warning_events,
        "dependency_unhealthy_count": dependency_unhealthy_count,
        "insufficient_data": insufficient,
        "thresholds": {
            "unhealthy_rate": unhealthy_threshold,
            "error_rate": error_threshold,
            "restart_rate": restart_threshold,
            "event_count": event_count_threshold,
            "latency_p95_ms": latency_p95_threshold_ms,
            "latency_p99_ms": latency_p99_threshold_ms,
            "availability_rate": availability_threshold,
            "readiness_rate": readiness_threshold,
        },
    })
