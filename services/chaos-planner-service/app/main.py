from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, status
from pydantic_settings import BaseSettings, SettingsConfigDict

from services.shared.chaos.safety import default_policy, validate_plan
from services.shared.chaos.schemas import ChaosPlanRequest
from services.shared.chaos.templates import build_manifest
from services.shared.storage.clickhouse_client import ClickHouseClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    topology_service_url: str = "http://topology-service.cascade-system.svc.cluster.local:8004"
    retrieval_service_url: str = "http://retrieval-service.cascade-system.svc.cluster.local:8012"
    request_timeout_seconds: float = 10.0

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


settings = Settings()
clickhouse = ClickHouseClient()
app = FastAPI(title="Cascade Chaos Planner Service", version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    await clickhouse.initialize_schema()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "chaos-planner-service"}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    ch = await clickhouse.ping()
    topo = await _check(settings.topology_service_url)
    retrieval = await _check(settings.retrieval_service_url)
    response = {"status": "ok" if ch and topo and retrieval else "degraded", "service": "chaos-planner-service", "clickhouse": ch, "topology_service": topo, "retrieval_service": retrieval}
    if response["status"] != "ok":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=response)
    return response


@app.post("/plans")
async def create_plan(payload: ChaosPlanRequest) -> dict[str, Any]:
    plan = await _build_plan(payload)
    safety = validate_plan(plan, default_policy(), dry_run=payload.dry_run)
    plan.update({"status": "ready" if safety.allowed else "rejected", "safety_score": safety.safety_score, "risk_level": safety.risk_level, "safety_findings": safety.findings + safety.violations})
    await _insert_plan(plan)
    if not safety.allowed:
        await _insert_violation(plan["plan_id"], "", "plan_rejected", "high", "; ".join(safety.violations), payload.model_dump())
        raise HTTPException(status_code=400, detail={"status": "rejected", "plan_id": plan["plan_id"], "violations": safety.violations})
    logger.info("created chaos plan id=%s service=%s kind=%s", plan["plan_id"], plan["target_service"], plan["experiment_kind"])
    return _public_plan(plan)


@app.get("/plans")
async def plans(limit: int = 20, service: str | None = None, status: str | None = None) -> dict[str, Any]:
    rows = await clickhouse.recent_chaos_plans(limit, service, status)
    return {"plans": [_decode_plan(row) for row in rows], "count": len(rows)}


@app.get("/plans/{plan_id}")
async def get_plan(plan_id: str) -> dict[str, Any]:
    row = await clickhouse.chaos_plan(plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return _decode_plan(row)


@app.post("/plans/from-anomaly")
async def plan_from_anomaly(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    service = payload.get("target_service")
    anomaly_id = payload.get("anomaly_id")
    if not service:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            if anomaly_id:
                resp = await client.get(f"{settings.retrieval_service_url.rstrip('/')}/anomalies/{anomaly_id}")
                if resp.status_code < 500:
                    service = resp.json().get("anomaly", {}).get("service")
            else:
                resp = await client.get(f"{settings.retrieval_service_url.rstrip('/')}/anomalies/recent", params={"limit": 1})
                if resp.status_code < 500:
                    rows = resp.json().get("anomalies", [])
                    service = rows[0].get("service") if rows else None
    request = ChaosPlanRequest(
        objective=f"Validate {service or 'service'} resilience based on anomaly evidence",
        target_service=service or "recommendationservice",
        target_namespace=payload.get("target_namespace", "cascade-targets"),
        experiment_kind=payload.get("experiment_kind", "pod_kill"),
        duration_seconds=int(payload.get("duration_seconds", 30)),
        dry_run=bool(payload.get("dry_run", True)),
    )
    return await create_plan(request)


@app.post("/plans/{plan_id}/validate")
async def validate_existing_plan(plan_id: str) -> dict[str, Any]:
    row = await clickhouse.chaos_plan(plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    plan = _decode_plan(row)
    result = validate_plan(plan, default_policy(), dry_run=True)
    return {"plan_id": plan_id, **result.model_dump()}


async def _build_plan(payload: ChaosPlanRequest) -> dict[str, Any]:
    plan_id = "chaos_plan_" + uuid.uuid4().hex[:16]
    experiment_id = "chaos_exp_" + uuid.uuid4().hex[:16]
    manifest = build_manifest(payload.experiment_kind, experiment_id, payload.target_namespace, payload.target_service, payload.duration_seconds)
    blast = await _blast_radius(payload.target_service)
    selector = manifest.get("spec", {}).get("selector", {})
    return {
        "plan_id": plan_id,
        "experiment_id": experiment_id,
        "status": "draft",
        "plan_type": "controlled-chaos",
        "experiment_kind": payload.experiment_kind,
        "target_namespace": payload.target_namespace,
        "target_service": payload.target_service,
        "target_workload": payload.target_workload or "",
        "target_selector": selector,
        "duration_seconds": payload.duration_seconds,
        "blast_radius_score": blast["score"],
        "safety_score": 0.0,
        "risk_level": "unknown",
        "objective": payload.objective,
        "hypothesis": f"If {payload.target_service} loses one pod, user impact should remain bounded and recover automatically.",
        "expected_impact": f"At most one {payload.target_service} pod is disrupted; downstream blast radius estimate: {blast['affected_services']}.",
        "safety_policy": default_policy().model_dump(),
        "manifest": manifest,
        "safety_findings": [],
    }


async def _blast_radius(service: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.post(f"{settings.topology_service_url.rstrip('/')}/topology/impact", json={"root_service": service})
            if response.status_code < 500:
                data = response.json()
                affected = data.get("affected_services", [])
                return {"score": round(min(1.0, 0.1 + 0.1 * len(affected)), 2), "affected_services": affected}
    except Exception:
        pass
    return {"score": 0.25, "affected_services": []}


async def _insert_plan(plan: dict[str, Any]) -> None:
    now = _now()
    await clickhouse.insert_chaos_experiment_plan({
        "plan_id": plan["plan_id"],
        "created_at": now,
        "updated_at": now,
        "status": plan["status"],
        "plan_type": plan["plan_type"],
        "experiment_kind": plan["experiment_kind"],
        "target_namespace": plan["target_namespace"],
        "target_service": plan["target_service"],
        "target_workload": plan["target_workload"],
        "target_selector_json": _json(plan["target_selector"]),
        "duration_seconds": plan["duration_seconds"],
        "blast_radius_score": plan["blast_radius_score"],
        "safety_score": plan["safety_score"],
        "risk_level": plan["risk_level"],
        "objective": plan["objective"],
        "hypothesis": plan["hypothesis"],
        "expected_impact": plan["expected_impact"],
        "safety_policy_json": _json(plan["safety_policy"]),
        "manifest_json": _json(plan["manifest"]),
        "plan_json": _json(plan),
    })


async def _insert_violation(plan_id: str, run_id: str, kind: str, severity: str, message: str, request: dict[str, Any]) -> None:
    await clickhouse.insert_chaos_safety_violation({
        "violation_id": "chaos_violation_" + uuid.uuid4().hex[:16],
        "created_at": _now(),
        "plan_id": plan_id,
        "run_id": run_id,
        "violation_type": kind,
        "severity": severity,
        "message": message,
        "policy_json": _json(default_policy().model_dump()),
        "request_json": _json(request),
    })


async def _check(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.get(base_url.rstrip("/") + "/ready")
            if response.status_code == 404:
                response = await client.get(base_url.rstrip("/") + "/health")
            return response.status_code < 500
    except Exception:
        return False


def _decode_plan(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["target_selector"] = _loads(decoded.pop("target_selector_json", "{}"))
    decoded["safety_policy"] = _loads(decoded.pop("safety_policy_json", "{}"))
    decoded["manifest"] = _loads(decoded.pop("manifest_json", "{}"))
    decoded["plan"] = _loads(decoded.pop("plan_json", "{}"))
    return decoded


def _public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "plan_id": plan["plan_id"],
        "status": plan["status"],
        "risk_level": plan["risk_level"],
        "safety_score": plan["safety_score"],
        "blast_radius_score": plan["blast_radius_score"],
        "manifest": plan["manifest"],
        "safety_findings": plan["safety_findings"],
        "plan": plan,
    }


def _loads(value: Any) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
