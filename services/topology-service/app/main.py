from __future__ import annotations

from fastapi import FastAPI

from app.models import HealthResponse, ImpactRequest, ImpactResponse, TopologyResponse
from app.topology import DEPENDENCIES, downstream, impact, upstream

app = FastAPI(title="Cascade Topology Service", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="topology-service")


@app.get("/topology", response_model=TopologyResponse)
async def topology() -> TopologyResponse:
    return TopologyResponse(dependencies=DEPENDENCIES)


@app.get("/topology/{service_name}/downstream")
async def downstream_services(service_name: str) -> dict[str, list[str]]:
    return {"service_name": service_name, "downstream": downstream(service_name)}


@app.get("/topology/{service_name}/upstream")
async def upstream_services(service_name: str) -> dict[str, list[str]]:
    return {"service_name": service_name, "upstream": upstream(service_name)}


@app.post("/topology/impact", response_model=ImpactResponse)
async def topology_impact(payload: ImpactRequest) -> ImpactResponse:
    path, affected = impact(payload.root_service)
    return ImpactResponse(root_service=payload.root_service, impact_path=path, affected_services=affected)
