from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from services.shared.anomaly.models import ModelResult
from services.shared.events.mapping import stable_json
from services.shared.features.extraction import ch_datetime


def combine_results(window: dict[str, Any], results: list[ModelResult], publish_threshold: float = 0.4) -> dict[str, Any]:
    risk = max((result.risk_score for result in results), default=0.0)
    is_anomaly = any(result.is_anomaly for result in results) or risk >= publish_threshold
    insufficient = any((result.evidence or {}).get("status") == "insufficient_data" or (result.evidence or {}).get("insufficient_data") for result in results)
    severity = severity_for_risk(risk)
    explanation = " | ".join(result.explanation for result in results if result.explanation)
    evidence = {
        "models": [
            {
                "model_name": result.model_name,
                "detector_type": result.detector_type,
                "is_anomaly": result.is_anomaly,
                "score": result.score,
                "risk_score": result.risk_score,
                "evidence": result.evidence,
            }
            for result in results
        ]
    }
    anomaly_id = stable_anomaly_id(str(window.get("window_id")), evidence)
    detected_at = datetime.now(UTC)
    return {
        "anomaly_id": anomaly_id,
        "detected_at": ch_datetime(detected_at),
        "window_id": str(window.get("window_id") or ""),
        "service": str(window.get("service") or "unknown"),
        "namespace": str(window.get("namespace") or "unknown"),
        "workload": str(window.get("workload") or ""),
        "window_start": str(window.get("window_start") or ch_datetime(detected_at)),
        "window_end": str(window.get("window_end") or ch_datetime(detected_at)),
        "severity": severity,
        "status": "detected" if is_anomaly else "insufficient_data" if insufficient else "normal",
        "anomaly_score": max((abs(result.score) for result in results), default=0.0),
        "risk_score": risk,
        "model_name": "cascade_baseline_ensemble",
        "model_version": "phase4.v1",
        "detector_type": "ensemble",
        "is_anomaly": 1 if is_anomaly else 0,
        "explanation": explanation[:4000],
        "evidence_json": stable_json(evidence),
        "feature_vector_json": str(window.get("feature_vector_json") or "{}"),
        "related_experiment_id": "",
        "published_to_redpanda": 0,
    }


def anomaly_event_payload(row: dict[str, Any]) -> dict[str, Any]:
    evidence = {}
    try:
        import json
        evidence = json.loads(row.get("evidence_json") or "{}")
    except Exception:
        evidence = {}
    try:
        import json
        feature_vector = json.loads(row.get("feature_vector_json") or "{}")
    except Exception:
        feature_vector = {}
    return {
        "schema_version": "phase4.v1",
        "event_type": "anomaly.detected",
        "anomaly_id": row["anomaly_id"],
        "detected_at": row["detected_at"],
        "service": row["service"],
        "namespace": row["namespace"],
        "workload": row["workload"],
        "window_start": row["window_start"],
        "window_end": row["window_end"],
        "severity": row["severity"],
        "risk_score": row["risk_score"],
        "anomaly_score": row["anomaly_score"],
        "models": evidence.get("models", []),
        "explanation": row["explanation"],
        "feature_vector": feature_vector,
        "related_experiment_id": row.get("related_experiment_id") or None,
    }


def severity_for_risk(risk: float) -> str:
    if risk >= 0.85:
        return "critical"
    if risk >= 0.65:
        return "high"
    if risk >= 0.40:
        return "medium"
    if risk >= 0.20:
        return "low"
    return "normal"


def stable_anomaly_id(window_id: str, evidence: dict[str, Any]) -> str:
    key = f"{window_id}|{stable_json(evidence)}"
    return "anomaly-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
