from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic_settings import BaseSettings, SettingsConfigDict

from services.shared.kafka.config import KafkaSettings
from services.shared.kafka.producer import KafkaProducer
from services.shared.remediation.approval import is_approval_current
from services.shared.remediation.events import remediation_event
from services.shared.remediation.safety import validate_approval
from services.shared.remediation.schemas import ApprovalRequest
from services.shared.storage.clickhouse_client import ClickHouseClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    kafka_bootstrap_servers: str = "redpanda.cascade-system.svc.cluster.local:9092"
    remediation_events_topic: str = "remediation.actions"
    remediation_publish_events: bool = True

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


settings = Settings()
clickhouse = ClickHouseClient()
producer = KafkaProducer(KafkaSettings(kafka_bootstrap_servers=settings.kafka_bootstrap_servers, kafka_client_id="approval-service"))
app = FastAPI(title="Cascade Approval Service", version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    await clickhouse.initialize_schema()
    if settings.remediation_publish_events:
        await producer.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    if settings.remediation_publish_events:
        await producer.stop()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "approval-service"}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    ch = await clickhouse.ping()
    response = {"status": "ok" if ch else "degraded", "service": "approval-service", "clickhouse": ch}
    if not ch:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=response)
    return response


@app.post("/approvals")
async def decide(payload: ApprovalRequest) -> dict[str, Any]:
    violations = validate_approval(payload.decision, payload.approver, payload.reason)
    if violations:
        raise HTTPException(status_code=400, detail={"violations": violations})
    plan_row = await clickhouse.remediation_plan(payload.plan_id)
    plan_type = "remediation"
    if plan_row is None:
        plan_row = await clickhouse.chaos_plan(payload.plan_id)
        plan_type = "chaos"
    if plan_row is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    approval = {
        "approval_id": "rem_approval_" + uuid.uuid4().hex[:16],
        "plan_id": payload.plan_id,
        "decided_at": _now(),
        "decision": payload.decision,
        "approver": payload.approver,
        "approver_role": payload.approver_role,
        "reason": payload.reason,
        "expires_at": _future(payload.expires_minutes) if payload.decision == "approved" else None,
        "metadata": {"source": "approval-service", "plan_type": plan_type, "expires_minutes": payload.expires_minutes},
    }
    await clickhouse.insert_remediation_approval({
        "approval_id": approval["approval_id"],
        "plan_id": approval["plan_id"],
        "decided_at": approval["decided_at"],
        "decision": approval["decision"],
        "approver": approval["approver"],
        "approver_role": approval["approver_role"],
        "reason": approval["reason"],
        "expires_at": approval["expires_at"],
        "approval_metadata_json": _json(approval["metadata"]),
    })
    event_type = "remediation.approved" if payload.decision == "approved" else "remediation.rejected"
    await _publish(event_type, _decode_plan(plan_row, plan_type), approval, payload.reason)
    logger.info("approval decision=%s plan_id=%s approval_id=%s", payload.decision, payload.plan_id, approval["approval_id"])
    return {"approval": approval}


@app.get("/approvals")
async def approvals(limit: int = 20, plan_id: str | None = None) -> dict[str, Any]:
    rows = await clickhouse.recent_remediation_approvals(limit, plan_id)
    return {"approvals": [_decode_approval(row) for row in rows], "count": len(rows)}


@app.get("/approvals/{approval_id}")
async def approval_detail(approval_id: str) -> dict[str, Any]:
    row = await clickhouse.remediation_approval(approval_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return {"approval": _decode_approval(row)}


@app.get("/plans/{plan_id}/approval-status")
async def approval_status(plan_id: str) -> dict[str, Any]:
    row = await clickhouse.latest_remediation_approval(plan_id)
    approval = _decode_approval(row) if row else None
    return {"plan_id": plan_id, "approval": approval, "approved": is_approval_current(approval), "approval_current": is_approval_current(approval)}


async def _publish(event_type: str, plan: dict[str, Any], approval: dict[str, Any], summary: str) -> None:
    if not settings.remediation_publish_events:
        return
    try:
        await producer.send(settings.remediation_events_topic, remediation_event(event_type, plan=plan, approval=approval, summary=summary), key=approval.get("approval_id"))
    except Exception as exc:
        logger.warning("Failed to publish approval event type=%s error=%s", event_type, exc)


def _decode_approval(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["metadata"] = _loads(decoded.pop("approval_metadata_json", "{}"))
    decoded["approval_current"] = is_approval_current(decoded)
    return decoded


def _decode_plan(row: dict[str, Any], plan_type: str = "remediation") -> dict[str, Any]:
    decoded = dict(row)
    if plan_type == "chaos":
        for key in ["target_selector_json", "safety_policy_json", "manifest_json", "plan_json"]:
            decoded[key.replace("_json", "")] = _loads(decoded.pop(key, "{}"))
        return decoded
    for key in ["remediation_steps_json", "rollback_steps_json", "evidence_refs_json", "safety_findings_json", "dry_run_manifest_json", "plan_json"]:
        decoded[key.replace("_json", "")] = _loads(decoded.pop(key, "{}"))
    return decoded


def _loads(value: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _future(minutes: int) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
