from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic_settings import BaseSettings, SettingsConfigDict

from services.shared.kafka.config import KafkaSettings
from services.shared.kafka.producer import KafkaProducer
from services.shared.live_demo import LiveDemoConfig, validate_live_demo_gate
from services.shared.remediation.approval import is_approval_current
from services.shared.remediation.dry_run import KubernetesRemediationClient, local_dry_run
from services.shared.remediation.events import remediation_event
from services.shared.remediation.safety import default_policy, validate_plan
from services.shared.remediation.schemas import ExecutionRequest
from services.shared.storage.clickhouse_client import ClickHouseClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    kafka_bootstrap_servers: str = "redpanda.cascade-system.svc.cluster.local:9092"
    remediation_events_topic: str = "remediation.actions"
    remediation_publish_events: bool = True
    execution_enabled: bool = False
    enable_dangerous_actions: bool = False
    enable_real_remediation: bool = False
    cascade_live_demo_mode: bool = False
    cascade_allowed_cluster_context: str = "kind-cascade"
    cascade_active_cluster_context: str = ""
    cascade_allowed_target_namespace: str = "cascade-targets"
    cascade_require_approval: bool = True
    cascade_require_dry_run_first: bool = True

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


settings = Settings()
clickhouse = ClickHouseClient()
producer = KafkaProducer(KafkaSettings(kafka_bootstrap_servers=settings.kafka_bootstrap_servers, kafka_client_id="remediation-executor-service"))
kube: KubernetesRemediationClient | None = None
app = FastAPI(title="Cascade Remediation Executor Service", version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    global kube
    await clickhouse.initialize_schema()
    try:
        kube = KubernetesRemediationClient()
    except Exception as exc:
        logger.warning("Kubernetes remediation client unavailable: %s", exc)
        kube = None
    if settings.remediation_publish_events:
        await producer.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    if settings.remediation_publish_events:
        await producer.stop()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "remediation-executor-service", **_live_status()}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    ch = await clickhouse.ping()
    kube_ready = bool(kube and kube.ready())
    response = {"status": "ok" if ch else "degraded", "service": "remediation-executor-service", "clickhouse": ch, "kubernetes": kube_ready, "execution_enabled": settings.execution_enabled, **_live_status()}
    if not ch:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=response)
    return response


@app.get("/safety/policy")
async def safety_policy() -> dict[str, Any]:
    policy = default_policy()
    data = policy.model_dump()
    data["execution_enabled"] = settings.execution_enabled
    data.update(_live_status())
    data["denied"] = {"namespaces": policy.denied_namespaces, "services": policy.denied_services, "resource_kinds": policy.denied_resource_kinds}
    data["protected"] = {"services": policy.protected_services}
    return data


@app.post("/executions/dry-run")
async def dry_run_execution(payload: ExecutionRequest) -> dict[str, Any]:
    plan = await _load_plan(payload.plan_id)
    safety = validate_plan(plan, default_policy(), approved=False, dry_run=True, execution_enabled=settings.execution_enabled)
    await _audit(plan, safety)
    if not safety.allowed:
        await _violation(plan["plan_id"], "", "dry_run_rejected", "high", "; ".join(safety.violations), payload.model_dump())
        raise HTTPException(status_code=400, detail={"status": "rejected", "violations": safety.violations})
    await _publish("remediation.dry_run.started", plan, {}, {}, "Dry-run validation started")
    result = local_dry_run(plan, kube)
    execution = _execution(plan, payload.approval_id, True, False, "completed" if result["validation_status"] in {"passed", "degraded"} else "failed", result["validation_status"], "not_executed", result["summary"], "", result["output"])
    await _insert_execution(execution)
    await _publish("remediation.dry_run.completed", plan, {}, execution, result["summary"])
    return {"execution": execution, "safety": safety.model_dump()}


@app.post("/executions")
async def execute(payload: ExecutionRequest) -> dict[str, Any]:
    plan = await _load_plan(payload.plan_id)
    approval = await _load_approval(payload.approval_id)
    approved = bool(approval and approval.get("plan_id") == plan["plan_id"] and is_approval_current(approval))
    safety = validate_plan(plan, default_policy(), approved=approved, dry_run=payload.dry_run, execution_enabled=settings.execution_enabled)
    await _audit(plan, safety)
    if payload.dry_run:
        return await dry_run_execution(payload)
    if not safety.allowed:
        execution = _execution(plan, payload.approval_id, False, False, "rejected", "not_started", "blocked", "; ".join(safety.violations), "; ".join(safety.violations), {})
        await _insert_execution(execution)
        await _violation(plan["plan_id"], execution["execution_id"], "execution_rejected", "high", "; ".join(safety.violations), payload.model_dump())
        await _publish("remediation.execution.failed", plan, approval or {}, execution, "; ".join(safety.violations))
        raise HTTPException(status_code=400, detail={"status": "rejected", "violations": safety.violations, "execution_id": execution["execution_id"]})

    dry_run_passed = await _dry_run_passed(plan["plan_id"])
    live_violations = validate_live_demo_gate(
        action="ENABLE_REAL_REMEDIATION",
        namespace=plan["namespace"],
        service=plan["service"],
        config=_live_config(),
        feature_enabled=settings.enable_real_remediation,
        approval_current=approved,
        dry_run_passed=dry_run_passed,
        current_context=kube.current_context() if kube else "",
    )
    if live_violations:
        execution = _execution(plan, payload.approval_id, False, False, "rejected", "not_started", "blocked", "; ".join(live_violations), "; ".join(live_violations), {})
        await _insert_execution(execution)
        await _violation(plan["plan_id"], execution["execution_id"], "live_demo_gate_rejected", "high", "; ".join(live_violations), payload.model_dump())
        await _publish("remediation.execution.failed", plan, approval or {}, execution, "; ".join(live_violations))
        raise HTTPException(status_code=400, detail={"status": "rejected", "violations": live_violations, "execution_id": execution["execution_id"]})

    dry = local_dry_run(plan, kube)
    if dry["validation_status"] not in {"passed", "degraded"}:
        execution = _execution(plan, payload.approval_id, False, False, "failed", dry["validation_status"], "not_executed", dry["summary"], dry["summary"], dry["output"])
        await _insert_execution(execution)
        await _publish("remediation.execution.failed", plan, approval or {}, execution, dry["summary"])
        raise HTTPException(status_code=400, detail={"status": "failed", "validation": dry})

    await _publish("remediation.execution.started", plan, approval or {}, {}, "Execution started")
    try:
        output = _execute_allowed(plan)
        execution = _execution(plan, payload.approval_id, False, True, "completed", "passed", "executed", "Execution completed", "", output)
        await _insert_execution(execution)
        await _publish("remediation.execution.completed", plan, approval or {}, execution, "Execution completed")
        return {"execution": execution}
    except Exception as exc:
        execution = _execution(plan, payload.approval_id, False, False, "failed", "passed", "failed", str(exc), str(exc), {})
        await _insert_execution(execution)
        await _publish("remediation.execution.failed", plan, approval or {}, execution, str(exc))
        raise HTTPException(status_code=500, detail={"error": str(exc), "execution_id": execution["execution_id"]})


@app.get("/executions")
async def executions(limit: int = 20, plan_id: str | None = None, status: str | None = None) -> dict[str, Any]:
    rows = await clickhouse.recent_remediation_executions(limit, plan_id, status)
    return {"executions": [_decode_execution(row) for row in rows], "count": len(rows)}


@app.get("/executions/{execution_id}")
async def execution_detail(execution_id: str) -> dict[str, Any]:
    row = await clickhouse.remediation_execution(execution_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return {"execution": _decode_execution(row)}


async def _load_plan(plan_id: str) -> dict[str, Any]:
    row = await clickhouse.remediation_plan(plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return _decode_plan(row)


async def _load_approval(approval_id: str) -> dict[str, Any] | None:
    if not approval_id:
        return None
    return await clickhouse.remediation_approval(approval_id)


async def _dry_run_passed(plan_id: str) -> bool:
    row = await clickhouse.latest_remediation_dry_run(plan_id)
    return bool(row)


def _execute_allowed(plan: dict[str, Any]) -> dict[str, Any]:
    if kube is None:
        raise RuntimeError("Kubernetes client unavailable")
    if plan["action_type"] == "restart_deployment":
        return kube.restart_deployment(plan["namespace"], plan["service"], plan["plan_id"])
    if plan["action_type"] == "scale_deployment_noop":
        return kube.scale_noop(plan["namespace"], plan["service"])
    raise RuntimeError(f"Action type {plan['action_type']} is not implemented for real execution")


def _execution(plan: dict[str, Any], approval_id: str, dry_run: bool, executed: bool, status_: str, validation: str, execution_status: str, summary: str, error: str, output: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    return {
        "execution_id": "rem_exec_" + uuid.uuid4().hex[:16],
        "plan_id": plan["plan_id"],
        "approval_id": approval_id or "",
        "started_at": now,
        "completed_at": now,
        "status": status_,
        "dry_run": dry_run,
        "executed": executed,
        "action_type": plan["action_type"],
        "namespace": plan["namespace"],
        "service": plan["service"],
        "resource_kind": "Deployment" if plan["action_type"] in {"restart_deployment", "scale_deployment_noop", "rollback_deployment"} else "",
        "resource_name": plan["service"],
        "validation_status": validation,
        "execution_status": execution_status,
        "rollback_available": bool(plan.get("rollback_steps")),
        "output_summary": summary[:1000],
        "error_message": error[:1000],
        "output": output,
    }


async def _insert_execution(execution: dict[str, Any]) -> None:
    await clickhouse.insert_remediation_execution({
        "execution_id": execution["execution_id"],
        "plan_id": execution["plan_id"],
        "approval_id": execution["approval_id"],
        "started_at": execution["started_at"],
        "completed_at": execution["completed_at"],
        "status": execution["status"],
        "dry_run": 1 if execution["dry_run"] else 0,
        "executed": 1 if execution["executed"] else 0,
        "action_type": execution["action_type"],
        "namespace": execution["namespace"],
        "service": execution["service"],
        "resource_kind": execution["resource_kind"],
        "resource_name": execution["resource_name"],
        "validation_status": execution["validation_status"],
        "execution_status": execution["execution_status"],
        "rollback_available": 1 if execution["rollback_available"] else 0,
        "output_summary": execution["output_summary"],
        "error_message": execution["error_message"],
        "execution_json": _json(execution),
    })


async def _audit(plan: dict[str, Any], result: Any) -> None:
    await clickhouse.insert_remediation_policy_audit({"audit_id": "rem_audit_" + uuid.uuid4().hex[:16], "checked_at": _now(), "plan_id": plan["plan_id"], "action_type": plan["action_type"], "namespace": plan["namespace"], "service": plan["service"], "allowed": 1 if result.allowed else 0, "risk_level": result.risk_level, "findings_json": _json(result.findings + result.violations), "policy_json": _json(default_policy().model_dump())})


async def _violation(plan_id: str, execution_id: str, kind: str, severity: str, message: str, request: dict[str, Any]) -> None:
    await clickhouse.insert_remediation_safety_violation({"violation_id": "rem_violation_" + uuid.uuid4().hex[:16], "created_at": _now(), "plan_id": plan_id, "execution_id": execution_id, "violation_type": kind, "severity": severity, "message": message, "policy_json": _json(default_policy().model_dump()), "request_json": _json(request)})


async def _publish(event_type: str, plan: dict[str, Any], approval: dict[str, Any], execution: dict[str, Any], summary: str) -> None:
    if not settings.remediation_publish_events:
        return
    try:
        await producer.send(settings.remediation_events_topic, remediation_event(event_type, plan=plan, approval=approval, execution=execution, summary=summary), key=execution.get("execution_id") or plan.get("plan_id"))
    except Exception as exc:
        logger.warning("Failed to publish execution event type=%s error=%s", event_type, exc)


def _live_config() -> LiveDemoConfig:
    return LiveDemoConfig(
        enable_dangerous_actions=settings.enable_dangerous_actions,
        enable_real_chaos=False,
        enable_real_remediation=settings.enable_real_remediation,
        cascade_live_demo_mode=settings.cascade_live_demo_mode,
        cascade_allowed_cluster_context=settings.cascade_allowed_cluster_context,
        cascade_active_cluster_context=settings.cascade_active_cluster_context,
        cascade_allowed_target_namespace=settings.cascade_allowed_target_namespace,
        cascade_require_approval=settings.cascade_require_approval,
        cascade_require_dry_run_first=settings.cascade_require_dry_run_first,
    )


def _live_status() -> dict[str, Any]:
    return {
        "dangerous_actions_enabled": settings.enable_dangerous_actions,
        "real_remediation_enabled": settings.enable_real_remediation,
        "live_demo_mode": settings.cascade_live_demo_mode,
        "allowed_cluster_context": settings.cascade_allowed_cluster_context,
        "active_cluster_context": settings.cascade_active_cluster_context or (kube.current_context() if kube else ""),
        "allowed_target_namespace": settings.cascade_allowed_target_namespace,
        "approval_required": settings.cascade_require_approval,
        "dry_run_first_required": settings.cascade_require_dry_run_first,
    }


def _decode_plan(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    for key in ["remediation_steps_json", "rollback_steps_json", "evidence_refs_json", "safety_findings_json", "dry_run_manifest_json", "plan_json"]:
        decoded[key.replace("_json", "")] = _loads(decoded.pop(key, "{}"))
    return decoded


def _decode_execution(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["dry_run"] = bool(decoded.get("dry_run"))
    decoded["executed"] = bool(decoded.get("executed"))
    decoded["rollback_available"] = bool(decoded.get("rollback_available"))
    decoded["execution"] = _loads(decoded.pop("execution_json", "{}"))
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
