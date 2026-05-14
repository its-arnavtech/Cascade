from __future__ import annotations

import logging
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from services.shared.embedding.deterministic import embed_text
from services.shared.events.mapping import build_memory_document, build_memory_payload, map_incident, map_incident_report, map_topology_snapshot
from services.shared.knowledge.context import assemble_context_pack
from services.shared.knowledge.search import KnowledgeSearchRequest
from services.shared.storage.clickhouse_client import ClickHouseClient
from services.shared.storage.qdrant_client import QdrantClient, QdrantSettings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    embedding_dimensions: int = 128
    qdrant_knowledge_collection: str = "cascade_knowledge_base"

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
knowledge_qdrant = QdrantClient(QdrantSettings(embedding_dimensions=settings.embedding_dimensions, qdrant_knowledge_collection=settings.qdrant_knowledge_collection))

app = FastAPI(title="Cascade Retrieval Service", version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    await clickhouse.initialize_schema()
    await qdrant.ensure_collection()
    await knowledge_qdrant.ensure_knowledge_collection()


@app.get("/health")
async def health() -> dict[str, Any]:
    clickhouse_ready = await clickhouse.ping()
    qdrant_ready = await qdrant.ping()
    collection_ready = await qdrant.collection_ready()
    knowledge_collection_ready = await knowledge_qdrant.knowledge_collection_ready()
    return {
        "status": "ok" if clickhouse_ready and qdrant_ready and collection_ready and knowledge_collection_ready else "degraded",
        "service": "retrieval-service",
        "clickhouse": clickhouse_ready,
        "qdrant": qdrant_ready,
        "collection": collection_ready,
        "knowledge_collection": knowledge_collection_ready,
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


@app.get("/features/recent")
async def features_recent(limit: int = 20, service: str | None = None) -> dict[str, Any]:
    rows = await clickhouse.recent_feature_windows(limit, service)
    return {"features": rows, "count": len(rows)}


@app.get("/anomalies/recent")
async def anomalies_recent(limit: int = 20, service: str | None = None, severity: str | None = None) -> dict[str, Any]:
    rows = await clickhouse.recent_anomalies(limit, service, severity)
    return {"anomalies": rows, "count": len(rows)}


@app.get("/anomalies/service/{service_name}")
async def anomalies_service(service_name: str, limit: int = 50) -> dict[str, Any]:
    rows = await clickhouse.service_anomalies(service_name, limit)
    return {"service": service_name, "anomalies": rows, "count": len(rows)}


@app.get("/anomalies/{anomaly_id}")
async def anomaly_detail(anomaly_id: str) -> dict[str, Any]:
    anomaly = await clickhouse.anomaly_detail(anomaly_id)
    if anomaly is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Anomaly not found")
    return {"anomaly": anomaly}


@app.post("/knowledge/search")
async def knowledge_search(payload: KnowledgeSearchRequest) -> dict[str, Any]:
    started = time.perf_counter()
    query_id = "kq_" + uuid.uuid4().hex[:20]
    vector = embed_text(payload.query, settings.embedding_dimensions)
    filters = payload.filters.model_dump()
    raw_results = await knowledge_qdrant.search_knowledge(vector, payload.limit, filters)
    results = await enrich_knowledge_results(raw_results)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    response = {"query_id": query_id, "query": payload.query, "results": results, "count": len(results), "latency_ms": latency_ms}
    await record_knowledge_query(query_id, payload.query, filters, results, latency_ms, response)
    return response


@app.post("/knowledge/context")
async def knowledge_context(payload: KnowledgeSearchRequest) -> dict[str, Any]:
    search = await knowledge_search(payload)
    return assemble_context_pack(payload.query, search["results"])


@app.get("/knowledge/stats")
async def knowledge_stats() -> dict[str, Any]:
    return {**await clickhouse.knowledge_stats(), "qdrant_knowledge_points": await knowledge_qdrant.count(settings.qdrant_knowledge_collection)}


@app.get("/knowledge/documents/recent")
async def knowledge_documents_recent(limit: int = 20) -> dict[str, Any]:
    rows = await clickhouse.recent_knowledge_documents(limit)
    return {"documents": [decode_knowledge_row(row) for row in rows], "count": len(rows)}


@app.get("/knowledge/runs/recent")
async def knowledge_runs_recent(limit: int = 20) -> dict[str, Any]:
    rows = await clickhouse.recent_knowledge_runs(limit)
    return {"runs": rows, "count": len(rows)}


@app.get("/debug/counts")
async def debug_counts() -> dict[str, Any]:
    tables = [
        "telemetry_events",
        "experiment_events",
        "incidents",
        "incident_reports",
        "topology_snapshots",
        "telemetry_feature_windows",
        "anomaly_events",
        "model_runs",
        "knowledge_documents",
        "knowledge_chunks",
        "knowledge_ingestion_runs",
        "knowledge_queries",
    ]
    counts = {}
    for table in tables:
        try:
            counts[table] = await clickhouse.count(table)
        except Exception:
            counts[table] = None
    counts["qdrant_points"] = await qdrant.count()
    try:
        counts["qdrant_knowledge_points"] = await knowledge_qdrant.count(settings.qdrant_knowledge_collection)
    except Exception:
        counts["qdrant_knowledge_points"] = None
    return counts


async def index_memory(memory_type: str, payload: dict[str, Any], source: str, source_topic: str = "") -> dict[str, Any]:
    await qdrant.ensure_collection()
    memory_payload = build_memory_payload(memory_type, payload, source, source_topic)
    vector = embed_text(build_memory_document(memory_type, payload), settings.embedding_dimensions)
    await qdrant.upsert_point(memory_payload["memory_id"], vector, memory_payload)
    return memory_payload


async def enrich_knowledge_results(raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunk_ids = [item.get("payload", {}).get("chunk_id", "") for item in raw_results if item.get("payload", {}).get("chunk_id")]
    rows = {row["chunk_id"]: decode_knowledge_row(row) for row in await clickhouse.knowledge_chunks_by_ids(chunk_ids)}
    results = []
    for item in raw_results:
        payload = item.get("payload", {})
        chunk_id = payload.get("chunk_id", "")
        row = rows.get(chunk_id, {})
        results.append({
            "score": item.get("score", 0.0),
            "chunk_id": chunk_id,
            "document_id": payload.get("document_id", row.get("document_id", "")),
            "title": payload.get("title", row.get("title", "")),
            "source_type": payload.get("source_type", row.get("source_type", "")),
            "document_type": payload.get("document_type", row.get("document_type", "")),
            "source_path": payload.get("source_path", row.get("source_path", "")),
            "source_uri": payload.get("source_uri", ""),
            "service": payload.get("service", row.get("service", "")),
            "namespace": payload.get("namespace", row.get("namespace", "")),
            "severity": payload.get("severity", row.get("severity", "")),
            "phase": payload.get("phase", row.get("phase", "")),
            "chunk_text": row.get("chunk_text", payload.get("compact_text", "")),
            "metadata": row.get("metadata", {}),
        })
    return results


async def record_knowledge_query(query_id: str, query: str, filters: dict[str, Any], results: list[dict[str, Any]], latency_ms: float, response: dict[str, Any]) -> None:
    await clickhouse.insert_knowledge_query({
        "query_id": query_id,
        "queried_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        "query_text": query,
        "filters_json": json.dumps(filters, sort_keys=True),
        "result_count": len(results),
        "top_score": float(results[0].get("score", 0.0)) if results else 0.0,
        "latency_ms": latency_ms,
        "response_json": json.dumps(response, sort_keys=True, default=str),
    })


def decode_knowledge_row(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    for source, target in [("tags_json", "tags"), ("metadata_json", "metadata")]:
        value = decoded.pop(source, None)
        if value is not None:
            try:
                decoded[target] = json.loads(value)
            except Exception:
                decoded[target] = value
    return decoded
