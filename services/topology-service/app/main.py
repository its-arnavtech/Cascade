from __future__ import annotations

from fastapi import FastAPI, Query

from app.models import BlastRadiusRequest, CriticalPathsRequest, DependenciesResponse, DirectionalServicesResponse, HealthResponse, ImpactRequest, ImpactResponse, TopologyResponse
from app.topology import DEPENDENCIES, blast_radius, critical_paths, dependencies, downstream, graph_payload, impact, upstream
from services.shared.targets.catalog import ACTIVE_TARGET

app = FastAPI(title="Cascade Topology Service", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="topology-service")


@app.get("/topology", response_model=TopologyResponse)
async def topology() -> TopologyResponse:
    return TopologyResponse(dependencies=DEPENDENCIES)


@app.get("/topology/graph")
async def topology_graph() -> dict:
    return graph_payload()


@app.get("/target/workload")
async def target_workload() -> dict:
    return {
        "name": ACTIVE_TARGET.name,
        "namespace": ACTIVE_TARGET.namespace,
        "frontend_service": ACTIVE_TARGET.frontend_service,
        "services": list(ACTIVE_TARGET.services),
        "dependency_edges": [list(edge) for edge in ACTIVE_TARGET.dependency_edges],
        "dependencies": ACTIVE_TARGET.dependencies,
        "safe_chaos_services": list(ACTIVE_TARGET.safe_chaos_services),
        "protected_services": list(ACTIVE_TARGET.protected_services),
        "load_generator": {
            "name": ACTIVE_TARGET.load_generator.name,
            "image": ACTIVE_TARGET.load_generator.image,
            "target_url": ACTIVE_TARGET.load_generator.target_url,
            "users": ACTIVE_TARGET.load_generator.users,
            "spawn_rate": ACTIVE_TARGET.load_generator.spawn_rate,
        },
    }


@app.get("/topology/{service_name}/downstream", response_model=DirectionalServicesResponse)
async def downstream_services(service_name: str) -> DirectionalServicesResponse:
    return DirectionalServicesResponse(service_name=service_name, downstream=downstream(service_name))


@app.get("/topology/{service_name}/upstream", response_model=DirectionalServicesResponse)
async def upstream_services(service_name: str) -> DirectionalServicesResponse:
    return DirectionalServicesResponse(service_name=service_name, upstream=upstream(service_name))


@app.get("/topology/{service_name}/dependencies", response_model=DependenciesResponse)
async def service_dependencies(
    service_name: str,
    hops: int = Query(default=2, ge=0, le=12),
    direction: str = Query(default="downstream", pattern="^(upstream|downstream)$"),
) -> DependenciesResponse:
    return DependenciesResponse(service_name=service_name, direction=direction, hops=hops, dependencies=dependencies(service_name, hops=hops, direction=direction))


@app.post("/topology/impact", response_model=ImpactResponse)
async def topology_impact(payload: ImpactRequest) -> ImpactResponse:
    path, affected = impact(payload.root_service)
    return ImpactResponse(root_service=payload.root_service, impact_path=path, affected_services=affected)


@app.post("/topology/blast-radius")
async def topology_blast_radius(payload: BlastRadiusRequest) -> dict:
    return blast_radius(payload.root_service, hops=payload.hops, depth_cap=payload.depth_cap)


@app.post("/topology/critical-paths")
async def topology_critical_paths(payload: CriticalPathsRequest) -> dict:
    return critical_paths(payload.root_service, depth_cap=payload.depth_cap, limit=payload.limit)
