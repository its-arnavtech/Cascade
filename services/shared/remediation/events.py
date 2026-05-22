from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.shared.contracts import RemediationExecution, RemediationPlan


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
    canonical_plan = RemediationPlan.from_legacy(plan) if plan.get("plan_id") else None
    canonical_execution = RemediationExecution.from_legacy(execution) if execution.get("execution_id") else None
    correlation_id = (
        execution.get("correlation_id")
        or plan.get("correlation_id")
        or (canonical_execution.correlation_id if canonical_execution else "")
        or (canonical_plan.correlation_id if canonical_plan else "")
        or execution.get("execution_id")
        or plan.get("plan_id")
        or ""
    )
    evidence = plan.get("evidence_refs") or []
    safety = plan.get("safety_findings") or execution.get("safety_findings") or []
    return {
        "schema_version": "phase8.v1",
        "contract_schema_version": RemediationExecution.model_fields["schema_version"].default,
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "correlation_id": correlation_id,
        "run_id": execution.get("run_id") or plan.get("run_id") or correlation_id,
        "plan_id": plan.get("plan_id") or approval.get("plan_id") or execution.get("plan_id") or "",
        "approval_id": approval.get("approval_id") or execution.get("approval_id") or "",
        "execution_id": execution.get("execution_id") or "",
        "policy_decision_id": (plan.get("policy_decision") or {}).get("policy_decision_id", "") if isinstance(plan.get("policy_decision"), dict) else "",
        "recommendation_id": plan.get("recommendation_id", ""),
        "rca_report_id": plan.get("rca_report_id", ""),
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

