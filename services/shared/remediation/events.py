from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def remediation_event(
    event_type: str,
    *,
    plan: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
    summary: str = "",
) -> dict[str, Any]:
    plan = plan or {}
    approval = approval or {}
    execution = execution or {}
    evidence = plan.get("evidence_refs") or []
    safety = plan.get("safety_findings") or execution.get("safety_findings") or []
    return {
        "schema_version": "phase8.v1",
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "plan_id": plan.get("plan_id") or approval.get("plan_id") or execution.get("plan_id") or "",
        "approval_id": approval.get("approval_id") or execution.get("approval_id") or "",
        "execution_id": execution.get("execution_id") or "",
        "trigger_type": plan.get("trigger_type", ""),
        "trigger_id": plan.get("trigger_id", ""),
        "service": plan.get("service") or execution.get("service") or "",
        "namespace": plan.get("namespace") or execution.get("namespace") or "",
        "action_type": plan.get("action_type") or execution.get("action_type") or "",
        "status": execution.get("status") or approval.get("decision") or plan.get("status") or "",
        "dry_run": bool(execution.get("dry_run", False)),
        "executed": bool(execution.get("executed", False)),
        "summary": summary[:500],
        "evidence_refs": evidence[:8],
        "safety_findings": safety[:8],
        "confidence": float(plan.get("confidence") or 0.0),
    }

