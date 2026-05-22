from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any

from services.shared.remediation.approval import is_approval_current


PLAN_HASH_FIELDS = (
    "plan_id",
    "action_type",
    "experiment_kind",
    "namespace",
    "target_namespace",
    "service",
    "target_service",
    "resource_kind",
    "resource_name",
    "manifest",
    "dry_run_manifest",
    "remediation_steps",
    "rollback_steps",
    "post_checks",
    "safety_policy",
)


def canonical_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: plan.get(key) for key in PLAN_HASH_FIELDS if key in plan}


def plan_hash(plan: dict[str, Any]) -> str:
    payload = json.dumps(canonical_plan(plan), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def approval_metadata(
    *,
    plan: dict[str, Any],
    plan_type: str,
    actor: str,
    risk_level: str,
    policy_decision: dict[str, Any] | None,
    expires_minutes: int,
    signing_secret: str = "",
) -> dict[str, Any]:
    nonce = secrets.token_urlsafe(18)
    digest = plan_hash(plan)
    metadata: dict[str, Any] = {
        "source": "approval-service",
        "plan_type": plan_type,
        "expires_minutes": expires_minutes,
        "actor": actor or "unknown",
        "target_action": plan.get("action_type") or plan.get("experiment_kind") or "",
        "target_service": plan.get("service") or plan.get("target_service") or "",
        "target_namespace": plan.get("namespace") or plan.get("target_namespace") or "",
        "risk_level": risk_level or plan.get("risk_level") or "unknown",
        "policy_decision": policy_decision or {},
        "policy_decision_id": str((policy_decision or {}).get("policy_decision_id") or ""),
        "plan_hash": digest,
        "nonce": nonce,
        "approval_binding_version": 1,
    }
    if signing_secret:
        metadata["signature"] = sign_approval(plan_id=str(plan.get("plan_id") or ""), plan_hash=digest, nonce=nonce, signing_secret=signing_secret)
    return metadata


def approval_valid_for_plan(approval: dict[str, Any] | None, plan: dict[str, Any], *, signing_secret: str = "") -> tuple[bool, list[str]]:
    if not is_approval_current(approval):
        return False, ["approval is missing, rejected, expired, or not current"]
    assert approval is not None
    if approval.get("plan_id") != plan.get("plan_id"):
        return False, ["approval is for a different plan"]
    metadata = approval.get("metadata")
    if not isinstance(metadata, dict):
        metadata = _loads(approval.get("approval_metadata_json", "{}"))
    if not isinstance(metadata, dict):
        return False, ["approval metadata is unavailable"]
    expected_hash = plan_hash(plan)
    if metadata.get("plan_hash") != expected_hash:
        return False, ["approval does not match the current plan contents"]
    nonce = str(metadata.get("nonce") or "")
    if not nonce:
        return False, ["approval nonce is missing"]
    signature = str(metadata.get("signature") or "")
    if signing_secret:
        expected = sign_approval(plan_id=str(plan.get("plan_id") or ""), plan_hash=expected_hash, nonce=nonce, signing_secret=signing_secret)
        if not signature or not hmac.compare_digest(signature, expected):
            return False, ["approval signature is invalid"]
    return True, []


def sign_approval(*, plan_id: str, plan_hash: str, nonce: str, signing_secret: str) -> str:
    message = f"{plan_id}:{plan_hash}:{nonce}".encode("utf-8")
    return hmac.new(signing_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _loads(value: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value
