from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from services.shared.embedding.deterministic import embed_text
from services.shared.events.mapping import build_memory_document, build_memory_payload, map_incident, map_incident_report, map_topology_snapshot
from services.shared.storage.clickhouse_client import ClickHouseClient
from services.shared.storage.qdrant_client import QdrantClient, QdrantSettings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    embedding_dimensions: int = 128

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=5, ge=1, le=50)
    service: str | None = None
    namespace: str | None = None
    memory_type: str | None = None


class MemoryIndexRequest(BaseModel):
    memory_type: str
    payload: dict[str, Any]
    source: str = "retrieval-service"
    source_topic: str = ""


class IncidentIngestRequest(BaseModel):
    incident: dict[str, Any]


class ReportIngestRequest(BaseModel):
    report: dict[str, Any]
    incident: dict[str, Any] | None = None


settings = Settings()
clickhouse = ClickHouseClient()
qdrant = QdrantClient(QdrantSettings(embedding_dimensions=settings.embedding_dimensions))

app = FastAPI(title="Cascade Retrieval Service", version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    await clickhouse.initialize_schema()
    await qdrant.ensure_collection()


@app.get("/health")
async def health() -> dict[str, Any]:
    clickhouse_ready = await clickhouse.ping()
    qdrant_ready = await qdrant.ping()
    collection_ready = await qdrant.collection_ready()
    return {
        "status": "ok" if clickhouse_ready and qdrant_ready and collection_ready else "degraded",
        "service": "retrieval-service",
        "clickhouse": clickhouse_ready,
        "qdrant": qdrant_ready,
        "collection": collection_ready,
    }


@app.get("/ready")
async def ready() -> dict[str, Any]:
    response = await health()
    if response["status"] != "ok":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=response)
    return response


@app.get("/events/recent")
async def events_recent(limit: int = 20, service: str | None = None, namespace: str | None = None, event_type: str | None = None) -> dict[str, Any]:
    rows = await clickhouse.recent_telemetry(limit, service, namespace, event_type)
    return {"events": rows, "count": len(rows)}


@app.get("/events/service/{service_name}")
async def events_service(service_name: str, limit: int = 50) -> dict[str, Any]:
    rows = await clickhouse.service_history(service_name, limit)
    return {"service": service_name, "events": rows, "count": len(rows)}


@app.get("/experiments/recent")
async def experiments_recent(limit: int = 20) -> dict[str, Any]:
    rows = await clickhouse.recent_experiments(limit)
    return {"experiments": rows, "count": len(rows)}


@app.get("/incidents/recent")
async def incidents_recent(limit: int = 20, service: str | None = None) -> dict[str, Any]:
    rows = await clickhouse.recent_incidents(limit, service)
    return {"incidents": rows, "count": len(rows)}


@app.get("/incidents/{incident_id}")
async def incident_detail(incident_id: str) -> dict[str, Any]:
    result = await clickhouse.incident_with_reports(incident_id)
    if result["incident"] is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return result


@app.post("/incidents")
async def ingest_incident(payload: IncidentIngestRequest) -> dict[str, Any]:
    row = map_incident(payload.incident)
    await clickhouse.insert_rows("incidents", [row])
    memory = await index_memory("reconstructed_incident", {**payload.incident, "incident_id": row["incident_id"]}, "incident-ingest")
    return {"status": "ok", "incident_id": row["incident_id"], "memory": memory}


@app.post("/reports")
async def ingest_report(payload: ReportIngestRequest) -> dict[str, Any]:
    row = map_incident_report(payload.report, payload.incident)
    await clickhouse.insert_rows("incident_reports", [row])
    source_payload = {**(payload.incident or {}), **payload.report, "incident_id": row["incident_id"], "report_id": row["report_id"]}
    memory = await index_memory("incident_report", source_payload, "report-ingest")
    return {"status": "ok", "report_id": row["report_id"], "incident_id": row["incident_id"], "memory": memory}


@app.post("/topology/snapshots")
async def ingest_topology(payload: dict[str, Any]) -> dict[str, Any]:
    row = map_topology_snapshot(payload)
    await clickhouse.insert_rows("topology_snapshots", [row])
    memory = await index_memory("topology_context", {**payload, "snapshot_id": row["snapshot_id"]}, "topology-ingest")
    return {"status": "ok", "snapshot_id": row["snapshot_id"], "memory": memory}


@app.post("/memory/search")
async def memory_search(payload: MemorySearchRequest) -> dict[str, Any]:
    vector = embed_text(payload.query, settings.embedding_dimensions)
    results = await qdrant.search(vector, payload.limit, payload.service, payload.namespace, payload.memory_type)
    return {"query": payload.query, "results": results, "count": len(results)}


@app.post("/memory/index")
async def memory_index(payload: MemoryIndexRequest) -> dict[str, Any]:
    memory = await index_memory(payload.memory_type, payload.payload, payload.source, payload.source_topic)
    return {"status": "ok", "memory": memory}


@app.get("/topology/snapshot/latest")
async def topology_latest() -> dict[str, Any]:
    snapshot = await clickhouse.latest_topology_snapshot()
    return {"snapshot": snapshot}


@app.get("/debug/counts")
async def debug_counts() -> dict[str, Any]:
    tables = ["telemetry_events", "experiment_events", "incidents", "incident_reports", "topology_snapshots"]
    counts = {}
    for table in tables:
        counts[table] = await clickhouse.count(table)
    counts["qdrant_points"] = await qdrant.count()
    return counts


async def index_memory(memory_type: str, payload: dict[str, Any], source: str, source_topic: str = "") -> dict[str, Any]:
    await qdrant.ensure_collection()
    memory_payload = build_memory_payload(memory_type, payload, source, source_topic)
    vector = embed_text(build_memory_document(memory_type, payload), settings.embedding_dimensions)
    await qdrant.upsert_point(memory_payload["memory_id"], vector, memory_payload)
    return memory_payload
