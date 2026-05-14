from __future__ import annotations

from typing import Any


def grade_for_score(score: float) -> str:
    if score >= 0.90:
        return "A"
    if score >= 0.75:
        return "B"
    if score >= 0.60:
        return "C"
    if score >= 0.40:
        return "D"
    return "F"


def compute_resilience_score(run: dict[str, Any], observation: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    anomalies = int(observation.get("anomaly_events_count", 0))
    incidents = int(observation.get("incidents_count", 0))
    affected = len(observation.get("affected_services", []) or [])
    cleanup_ok = run.get("cleanup_status") in {"cleaned_up", "not_required"}
    blast_radius = float(plan.get("blast_radius_score", 0.2))
    anomaly_penalty = min(0.25, anomalies * 0.04)
    incident_penalty = min(0.3, incidents * 0.12)
    blast_penalty = min(0.2, max(0, affected - 1) * 0.05 + blast_radius * 0.05)
    evidence_score = 0.1 if int(observation.get("telemetry_events_count", 0)) > 0 else 0.0
    recovery_score = 1.0 if cleanup_ok else 0.55
    score = 0.85 + evidence_score - anomaly_penalty - incident_penalty - blast_penalty
    if cleanup_ok:
        score += 0.05
    else:
        score -= 0.2
    score = round(max(0.0, min(1.0, score)), 2)
    recommendations = _recommendations(score, anomalies, incidents, cleanup_ok)
    return {
        "resilience_score": score,
        "recovery_score": recovery_score,
        "blast_radius_score": blast_radius,
        "anomaly_penalty": round(anomaly_penalty, 2),
        "incident_penalty": round(incident_penalty, 2),
        "evidence_score": evidence_score,
        "grade": grade_for_score(score),
        "explanation": f"Score reflects {anomalies} anomaly row(s), {incidents} incident row(s), {affected} affected service(s), and cleanup={cleanup_ok}.",
        "recommendations": recommendations,
    }


def _recommendations(score: float, anomalies: int, incidents: int, cleanup_ok: bool) -> list[str]:
    recs = ["Keep chaos experiments bounded to one service and review telemetry before increasing scope."]
    if anomalies:
        recs.append("Investigate anomaly evidence before repeating the same experiment.")
    if incidents:
        recs.append("Compare incident timeline and topology impact before planning remediation.")
    if not cleanup_ok:
        recs.append("Verify Chaos Mesh resource cleanup before running more experiments.")
    if score >= 0.9:
        recs.append("Service handled the bounded experiment well; consider a dry-run network-delay plan next.")
    return recs
