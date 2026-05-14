from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def chaos_event(event_type: str, plan: dict[str, Any] | None = None, run: dict[str, Any] | None = None, score: dict[str, Any] | None = None, summary: str = "") -> dict[str, Any]:
    plan = plan or {}
    run = run or {}
    score = score or {}
    return {
        "schema_version": "phase7.v1",
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "plan_id": run.get("plan_id") or plan.get("plan_id", ""),
        "run_id": run.get("run_id", ""),
        "experiment_id": run.get("experiment_id") or plan.get("experiment_id", ""),
        "experiment_kind": run.get("experiment_kind") or plan.get("experiment_kind", ""),
        "target_namespace": run.get("target_namespace") or plan.get("target_namespace", ""),
        "target_service": run.get("target_service") or plan.get("target_service", ""),
        "target_workload": run.get("target_workload") or plan.get("target_workload", ""),
        "dry_run": bool(run.get("dry_run", False)),
        "approved": bool(run.get("approved", False)),
        "status": run.get("status") or plan.get("status", ""),
        "resilience_score": float(score.get("resilience_score", 0.0)),
        "grade": score.get("grade", ""),
        "summary": summary[:500],
        "evidence_refs": score.get("evidence_refs", [])[:10] if isinstance(score.get("evidence_refs", []), list) else [],
    }
