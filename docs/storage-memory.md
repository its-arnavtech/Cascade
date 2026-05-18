# Storage and memory - Storage + Memory Layer

Storage and memory extends Cascade's completed Telemetry pipeline incident-intelligence pipeline with durable analytical storage and semantic memory. It persists enriched telemetry, experiment events, reconstructed incidents, incident reports, topology snapshots, and vector-searchable memory records.

## Architecture

```text
Prometheus -> observation-service -> telemetry.raw -> Redpanda
Redpanda -> stream-enricher -> telemetry.enriched -> telemetry-archiver -> ClickHouse
Chaos Mesh -> experiment-tracker-service -> experiments.events -> telemetry-archiver -> ClickHouse
causal-reconstruction-service + incident-timeline-service -> retrieval-service ingest APIs -> ClickHouse + Qdrant
telemetry.enriched + experiments.events -> memory-indexer -> Qdrant
retrieval-service -> ClickHouse + Qdrant
```

## Services

- `telemetry-archiver`: consumes `telemetry.enriched` and `experiments.events`, maps loose JSON defensively, and writes `telemetry_events` and `experiment_events`.
- `memory-indexer`: consumes `telemetry.enriched` and `experiments.events`, builds deterministic memory documents, embeds them locally, and upserts Qdrant points.
- `retrieval-service`: exposes storage/query APIs, persists incident/report/topology records, and searches Qdrant memory.
- `clickhouse`: single-node local analytical store for kind.
- `qdrant`: local vector database for incident memory.

## ClickHouse Schema

Database: `cascade`

Tables:

- `telemetry_events`: enriched telemetry rows ordered by `(service, observed_at, event_id)`.
- `experiment_events`: experiment lifecycle events ordered by `(experiment_id, observed_at, event_id)`.
- `incidents`: reconstructed incident metadata ordered by `(root_cause_service, first_seen_at, incident_id)`.
- `incident_reports`: generated reports ordered by `(root_cause_service, generated_at, report_id)`.
- `topology_snapshots`: topology context ordered by `(captured_at, snapshot_id)`.

All tables use `MergeTree` and are created idempotently by `infra/kubernetes/clickhouse/schema-job.yaml` and by service startup safeguards.

## Qdrant Collection

Collection: `cascade_incident_memory`

- Vector size: `128`
- Distance: `Cosine`
- Payload fields include `memory_id`, `memory_type`, `event_id`, `incident_id`, `experiment_id`, `service`, `namespace`, `workload`, `severity`, `health_status`, `event_type`, `root_cause_service`, `observed_at`, `generated_at`, `summary`, `source`, `source_topic`, `tags`, and `compact_json`.

Memory types:

- `telemetry_event`
- `experiment_event`
- `reconstructed_incident`
- `incident_report`
- `topology_context`

## Deterministic Embeddings

Storage and memory intentionally uses local deterministic embeddings. Text is lowercased, tokenized, hashed into a fixed 128-dimensional vector, signed, weighted, and L2-normalized. This requires no OpenAI key, paid API, or model download. It is a placeholder for future real embedding models in Knowledge and RAG.

## Retrieval API

`retrieval-service` listens on port `8012`.

- `GET /health`
- `GET /ready`
- `GET /events/recent?limit=&service=&namespace=&event_type=`
- `GET /events/service/{service_name}?limit=`
- `GET /experiments/recent?limit=`
- `GET /incidents/recent?limit=&service=`
- `GET /incidents/{incident_id}`
- `POST /incidents`
- `POST /reports`
- `POST /topology/snapshots`
- `POST /memory/search`
- `POST /memory/index`
- `GET /topology/snapshot/latest`
- `GET /debug/counts`

Example memory search:

```json
{
  "query": "unhealthy pod restart latency service failure experiment root cause",
  "limit": 5
}
```

## Deployment Workflow

```powershell
.\scripts\deploy-storage-memory.ps1
.\scripts\accept-storage-memory.ps1
.\scripts\demo-storage-memory.ps1
```

`deploy-storage-memory.ps1` is safe to rerun. It deploys Telemetry pipeline unless `-SkipTelemetryDeploy` is used, builds Storage and memory images, loads them into kind, deploys ClickHouse/Qdrant, runs idempotent init jobs, and deploys Storage and memory services.

## Acceptance Criteria

`accept-storage-memory.ps1` validates:

- Telemetry pipeline deployments and Redpanda topics exist.
- ClickHouse deployment, service endpoint, database, and tables exist.
- Qdrant deployment, service endpoint, and collection exist.
- Real `telemetry.enriched` rows reach ClickHouse.
- Real `experiments.events` rows reach ClickHouse.
- Incident/report/topology records can be stored through retrieval-service APIs.
- Qdrant has indexed points.
- Retrieval APIs return JSON and memory search returns results.

The script prints `STORAGE AND MEMORY ACCEPTANCE: PASS` only after those checks pass.

## Demo Workflow

`demo-storage-memory.ps1` creates an experiment, waits for archival, reconstructs an incident, generates a report, persists incident/report/topology records, prints ClickHouse/Qdrant counts, shows recent telemetry/experiment/incident records, and runs a similar-memory search.

## Troubleshooting

```powershell
.\scripts\debug-storage-memory.ps1
```

The debug script collects pods, deployments, services, endpoints, recent events, logs, Redpanda topics, ClickHouse tables/counts, Qdrant collection/count, and retrieval-service health/readiness.

## Known Limitations

- Deterministic local embeddings are placeholders.
- No ML anomaly detection yet.
- No RAG yet.
- No LangGraph or autonomous agents yet.
- No production persistence hardening yet.
- No frontend/UI yet.
