from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from .safety import default_policy, validate_plan
from .schemas import RemediationPlanRequest
from .templates import command_preview, dry_run_manifest, post_checks, pre_checks, remediation_steps, rollback_steps


def stable_id(prefix: str, seed: str) -> str:
    return f"{prefix}_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]


def build_plan(request: RemediationPlanRequest, evidence_refs: list[dict[str, Any]], context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    now = datetime.now(UTC).isoformat()
    seed = f"{now}:{request.trigger_type}:{request.trigger_id}:{request.service}:{request.namespace}:{request.objective}:{request.preferred_action_type}"
    plan_id = stable_id("rem_plan", seed)
    action_type = request.preferred_action_type or "investigate_only"
    severity = _severity(context)
    plan_body = {
        "title": f"Remediation recommendation for {request.service}",
        "summary": _summary(request, action_type, evidence_refs),
        "suspected_issue": _suspected_issue(context),
        "proposed_action": action_type,
        "pre_checks": pre_checks(request.service, request.namespace),
        "remediation_steps": remediation_steps(action_type, request.service, request.namespace),
        "post_checks": post_checks(request.service, request.namespace),
        "rollback_steps": rollback_steps(action_type, request.service, request.namespace),
        "command_preview": command_preview(action_type, request.service, request.namespace),
        "human_approval_required": action_type != "investigate_only",
        "evidence_refs": evidence_refs,
        "context_summary": context.get("summary", ""),
    }
    plan = {
        "plan_id": plan_id,
        "status": "ready",
        "trigger_type": request.trigger_type,
        "trigger_id": request.trigger_id,
        "source_investigation_id": request.trigger_id if request.trigger_type == "investigation" else context.get("source_investigation_id", ""),
        "source_anomaly_id": request.trigger_id if request.trigger_type == "anomaly" else context.get("source_anomaly_id", ""),
        "source_incident_id": request.trigger_id if request.trigger_type == "incident" else context.get("source_incident_id", ""),
        "source_chaos_run_id": request.trigger_id if request.trigger_type == "chaos" else context.get("source_chaos_run_id", ""),
        "service": request.service,
        "namespace": request.namespace,
        "severity": severity,
        "risk_score": 0.0,
        "confidence": _confidence(evidence_refs, context),
        "action_type": action_type,
        "action_summary": plan_body["summary"],
        "remediation_steps": plan_body["remediation_steps"],
        "rollback_steps": plan_body["rollback_steps"],
        "evidence_refs": evidence_refs,
        "safety_findings": [],
        "dry_run_manifest": dry_run_manifest(action_type, request.service, request.namespace),
        "plan": plan_body,
    }
    safety = validate_plan(plan, default_policy(), dry_run=True)
    plan["status"] = "ready" if safety.allowed else "rejected"
    plan["risk_score"] = safety.risk_score
    plan["safety_findings"] = safety.findings + safety.violations
    return plan


def _summary(request: RemediationPlanRequest, action_type: str, evidence_refs: list[dict[str, Any]]) -> str:
    if evidence_refs:
        return f"Use {action_type} for {request.service} with {len(evidence_refs)} evidence reference(s) and dry-run validation before any execution."
    return f"Evidence is limited; use {action_type} to gather more data for {request.service} before considering mutation."


def _suspected_issue(context: dict[str, Any]) -> str:
    for key in ["explanation", "summary", "suspected_root_cause", "final_summary"]:
        if context.get(key):
            return str(context[key])[:600]
    return "No single root cause is confirmed; recommendation remains conservative."


def _severity(context: dict[str, Any]) -> str:
    return str(context.get("severity") or context.get("risk_level") or "unknown")


def _confidence(evidence_refs: list[dict[str, Any]], context: dict[str, Any]) -> float:
    score = 0.25 + min(0.45, 0.12 * len(evidence_refs))
    if context.get("summary") or context.get("explanation"):
        score += 0.15
    return round(min(0.95, score), 2)

