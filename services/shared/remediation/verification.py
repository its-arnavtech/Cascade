from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from services.shared.remediation.schemas import RollbackPlan, VerificationResult

LOWER_IS_BETTER = {
    "restart_count",
    "warning_events_count",
    "event_count",
    "unhealthy_count",
    "warning_count",
    "error_count",
    "avg_cpu",
    "max_cpu",
    "avg_memory",
    "max_memory",
    "avg_latency_ms",
    "max_latency_ms",
    "error_rate",
    "restart_rate",
    "unhealthy_rate",
    "anomaly_count",
    "anomaly_risk_score",
    "anomaly_score",
}

HIGHER_IS_BETTER = {
    "available_replicas",
    "ready_replicas",
    "ready_pods",
    "availability",
    "healthy_count",
    "resilience_score",
    "recovery_score",
}

ROLLBACK_UNSUPPORTED_REASON = "Rollback is unavailable for this action type until Cascade captures a supported reversible resource snapshot."


def now_ts() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def build_health_snapshot(
    *,
    service: str,
    namespace: str,
    phase: str,
    kubernetes: dict[str, Any] | None = None,
    feature_windows: list[dict[str, Any]] | None = None,
    anomalies: list[dict[str, Any]] | None = None,
    resilience_scores: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    feature_windows = [row for row in feature_windows or [] if not namespace or str(row.get("namespace") or namespace) == namespace]
    anomalies = [row for row in anomalies or [] if not namespace or str(row.get("namespace") or namespace) == namespace]
    resilience_scores = [row for row in resilience_scores or [] if not namespace or str(row.get("namespace") or namespace) == namespace]
    kube = kubernetes or {}
    latest_features = feature_windows[0] if feature_windows else {}
    latest_anomaly = anomalies[0] if anomalies else {}
    latest_score = resilience_scores[0] if resilience_scores else {}
    metrics: dict[str, float] = {}

    for key in [
        "available_replicas",
        "ready_replicas",
        "ready_pods",
        "restart_count",
        "warning_events_count",
        "availability",
    ]:
        _put_float(metrics, key, kube.get(key))
    for key in [
        "event_count",
        "unhealthy_count",
        "healthy_count",
        "restart_signal_count",
        "warning_count",
        "error_count",
        "avg_cpu",
        "max_cpu",
        "avg_memory",
        "max_memory",
        "avg_latency_ms",
        "max_latency_ms",
        "error_rate",
        "restart_rate",
        "unhealthy_rate",
    ]:
        _put_float(metrics, key, latest_features.get(key))
    metrics["anomaly_count"] = float(len(anomalies))
    _put_float(metrics, "anomaly_risk_score", latest_anomaly.get("risk_score"))
    _put_float(metrics, "anomaly_score", latest_anomaly.get("anomaly_score"))
    _put_float(metrics, "resilience_score", latest_score.get("resilience_score"))
    _put_float(metrics, "recovery_score", latest_score.get("recovery_score"))

    evidence_count = int(bool(kube)) + len(feature_windows) + len(anomalies) + len(resilience_scores)
    resolved_limitations = list(limitations or [])
    if not kube:
        resolved_limitations.append("Kubernetes snapshot unavailable")
    if not feature_windows:
        resolved_limitations.append("No feature windows available for comparison")
    if not anomalies:
        resolved_limitations.append("No anomaly rows available for comparison")

    return {
        "captured_at": now_ts(),
        "phase": phase,
        "service": service,
        "namespace": namespace,
        "metrics": metrics,
        "evidence_count": evidence_count,
        "kubernetes": kube,
        "feature_window_count": len(feature_windows),
        "anomaly_count": len(anomalies),
        "resilience_score_count": len(resilience_scores),
        "latest_feature_window": latest_features,
        "latest_anomaly": latest_anomaly,
        "latest_resilience_score": latest_score,
        "limitations": resolved_limitations,
    }


def build_rollback_plan(plan: dict[str, Any], execution_id: str, before: dict[str, Any], created_at: str | None = None) -> RollbackPlan:
    created = created_at or now_ts()
    action_type = str(plan.get("action_type") or "")
    namespace = str(plan.get("namespace") or "")
    service = str(plan.get("service") or "")
    snapshot = _snapshot(before)
    rollback_type = ""
    actions: list[dict[str, Any]] = []
    available = False
    auto_executable = False
    reason = ROLLBACK_UNSUPPORTED_REASON

    if action_type in {"scale_deployment", "scale_deployment_noop"}:
        replicas = snapshot.get("replicas")
        if replicas is not None:
            rollback_type = "deployment_replicas"
            available = True
            auto_executable = True
            reason = "Previous deployment replica count was captured."
            actions = [{"action": "restore_deployment_replicas", "namespace": namespace, "deployment": service, "replicas": int(replicas)}]
        else:
            rollback_type = "deployment_replicas"
            reason = "Deployment replica count was not captured before execution."
    elif action_type == "restart_deployment":
        template = snapshot.get("template_metadata") or {}
        rollback_type = "deployment_template_metadata"
        if template:
            available = True
            reason = "Previous deployment template metadata was captured; automatic restart rollback is disabled by default."
            actions = [{"action": "restore_deployment_template_metadata", "namespace": namespace, "deployment": service, "template_metadata": template}]
        else:
            reason = "Deployment restart is non-reversible because previous deployment template metadata was not captured."
    elif action_type in {"patch_resource", "apply_config_patch", "change_hpa"}:
        rollback_type = action_type
        reason = "Rollback is unavailable until Cascade stores the previous resource body for this patch type."

    return RollbackPlan(
        rollback_plan_id="rollback_" + uuid.uuid4().hex[:16],
        execution_id=execution_id,
        plan_id=str(plan.get("plan_id") or ""),
        created_at=created,
        updated_at=created,
        action_type=action_type,
        namespace=namespace,
        service=service,
        rollback_type=rollback_type,
        available=available,
        auto_executable=auto_executable,
        status="available" if available else "unavailable",
        reason=reason,
        snapshot=snapshot,
        actions=actions,
    )


def evaluate_verification(
    *,
    plan: dict[str, Any],
    execution: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    rollback_plan: RollbackPlan | None = None,
    rollback_result: dict[str, Any] | None = None,
) -> VerificationResult:
    completed = now_ts()
    has_evidence = int(before.get("evidence_count") or 0) > 0 or int(after.get("evidence_count") or 0) > 0
    comparisons = compare_metrics(before.get("metrics") or {}, after.get("metrics") or {}) if has_evidence else []
    limitations = _dedupe(list(before.get("limitations") or []) + list(after.get("limitations") or []))
    execution_status = str(execution.get("status") or execution.get("execution_status") or "").lower()
    evidence_quality = "sufficient" if comparisons else "insufficient"
    rollback_status = rollback_plan.status if rollback_plan else "not_needed"
    status = "insufficient_evidence"
    has_evidence = int(before.get("evidence_count") or 0) + int(after.get("evidence_count") or 0) > 0

    if "fail" in execution_status:
        status = "failed"
    elif not has_evidence:
        status = "insufficient_evidence"
        limitations.append("No before/after evidence was available")
    elif not comparisons:
        status = "insufficient_evidence"
        limitations.append("No comparable before/after metrics were available")
    else:
        improved = [item for item in comparisons if item["direction"] == "improved"]
        degraded = [item for item in comparisons if item["direction"] == "degraded"]
        if degraded and len(degraded) >= len(improved):
            status = "degraded"
        elif improved:
            status = "fixed" if _looks_healthy(after.get("metrics") or {}) else "improved"
        else:
            status = "unchanged"

    if rollback_result:
        rollback_status = "executed" if rollback_result.get("status") == "executed" else "failed"
        if rollback_status == "executed":
            status = "rolled_back"

    summary = _summary(status, comparisons, rollback_status)
    return VerificationResult(
        verification_id="verify_" + uuid.uuid4().hex[:16],
        execution_id=str(execution.get("execution_id") or ""),
        plan_id=str(plan.get("plan_id") or ""),
        rollback_plan_id=rollback_plan.rollback_plan_id if rollback_plan else "",
        created_at=str(execution.get("completed_at") or completed),
        completed_at=completed,
        action_type=str(plan.get("action_type") or ""),
        namespace=str(plan.get("namespace") or ""),
        service=str(plan.get("service") or ""),
        status=status,
        evidence_quality=evidence_quality,
        rollback_status=rollback_status,
        summary=summary,
        before=before,
        after=after,
        comparisons=comparisons,
        limitations=_dedupe(limitations),
        rollback=rollback_result or (rollback_plan.model_dump() if rollback_plan else {}),
    )


def compare_metrics(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    comparisons = []
    for metric in sorted((set(before) & set(after)) & (LOWER_IS_BETTER | HIGHER_IS_BETTER)):
        try:
            before_value = float(before[metric])
            after_value = float(after[metric])
        except (TypeError, ValueError):
            continue
        if before_value == after_value:
            direction = "unchanged"
            delta = 0.0
        elif metric in LOWER_IS_BETTER:
            delta = before_value - after_value
            direction = "improved" if delta > 0 else "degraded"
        else:
            delta = after_value - before_value
            direction = "improved" if delta > 0 else "degraded"
        comparisons.append({"metric": metric, "before": before_value, "after": after_value, "delta": round(delta, 6), "direction": direction})
    return comparisons


def rollback_plan_row(plan: RollbackPlan) -> dict[str, Any]:
    return plan.model_dump()


def verification_result_row(result: VerificationResult) -> dict[str, Any]:
    return result.model_dump()


def _put_float(target: dict[str, float], key: str, value: Any) -> None:
    if value is None or value == "":
        return
    try:
        target[key] = float(value)
    except (TypeError, ValueError):
        return


def _snapshot(before: dict[str, Any]) -> dict[str, Any]:
    kube = before.get("kubernetes") or {}
    return {
        "replicas": kube.get("replicas"),
        "available_replicas": kube.get("available_replicas"),
        "ready_replicas": kube.get("ready_replicas"),
        "template_metadata": kube.get("template_metadata") or {},
        "captured_at": before.get("captured_at", ""),
    }


def _looks_healthy(metrics: dict[str, Any]) -> bool:
    return (
        float(metrics.get("anomaly_count", 0.0) or 0.0) == 0.0
        and float(metrics.get("error_rate", 0.0) or 0.0) == 0.0
        and float(metrics.get("unhealthy_rate", 0.0) or 0.0) == 0.0
    )


def _summary(status: str, comparisons: list[dict[str, Any]], rollback_status: str) -> str:
    changed = [item for item in comparisons if item["direction"] != "unchanged"]
    prefix = f"Verification result is {status}"
    if not changed:
        return f"{prefix}; no comparable metric changed. Rollback status: {rollback_status}."
    details = ", ".join(f"{item['metric']} {item['direction']}" for item in changed[:5])
    return f"{prefix}; {details}. Rollback status: {rollback_status}."


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in values if item))
