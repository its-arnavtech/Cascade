from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.shared.contracts import AutopilotRun

from .schemas import AutopilotRunRecord


def autopilot_event(event_type: str, run: AutopilotRunRecord, summary: str = "") -> dict[str, Any]:
    canonical = AutopilotRun.from_legacy(run)
    return {
        "schema_version": "autopilot.v1",
        "contract_schema_version": AutopilotRun.model_fields["schema_version"].default,
        "event_type": event_type,
        "event_id": f"{run.run_id}:{event_type}:{run.updated_at}",
        "emitted_at": datetime.now(UTC).isoformat(),
        "correlation_id": canonical.correlation_id,
        "run_id": run.run_id,
        "status": run.status,
        "final_result": run.final_result,
        "mode": run.mode,
        "trigger_type": run.trigger_type,
        "trigger_id": run.trigger_id,
        "service": run.service,
        "namespace": run.namespace,
        "anomaly_id": run.anomaly_id,
        "investigation_id": run.investigation_id,
        "recommendation_id": run.recommendation.get("recommendation_id", "") if isinstance(run.recommendation, dict) else "",
        "policy_decision_id": run.action.get("policy_decision_id", "") if isinstance(run.action, dict) else "",
        "remediation_plan_id": run.remediation_plan_id,
        "dry_run_execution_id": run.dry_run_execution_id,
        "execution_id": run.execution_id,
        "verification_id": run.verification.get("verification_id", "") if isinstance(run.verification, dict) else "",
        "rollback_plan_id": run.verification.get("rollback_plan_id", "") if isinstance(run.verification, dict) else "",
        "proposed_action": run.proposed_action,
        "summary": summary,
    }
