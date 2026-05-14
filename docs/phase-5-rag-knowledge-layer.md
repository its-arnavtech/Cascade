# Phase 5 - RAG + Knowledge Layer

Phase 5 adds a source-grounded operational knowledge layer to Cascade. It retrieves runbooks, architecture notes, incident reports, anomaly records, and topology context without using hosted APIs, LLMs, agents, or remediation execution.

## Architecture

```text
docs/runbooks/incidents/anomalies/topology
-> knowledge-ingestion-service
-> ClickHouse knowledge_documents / knowledge_chunks
-> Qdrant cascade_knowledge_base
-> knowledge-retrieval-service
-> retrieval-service knowledge APIs
```

## Data Flow

`knowledge-ingestion-service` reads repo documentation from `/app/knowledge`, plus operational rows from ClickHouse `incidents`, `incident_reports`, `anomaly_events`, and `topology_snapshots`. It chunks content, embeds chunks with the local deterministic embedding utility, stores metadata/content in ClickHouse, and upserts chunk vectors into Qdrant.

`knowledge-retrieval-service` embeds a query with the same deterministic utility, searches Qdrant collection `cascade_knowledge_base`, hydrates chunk text and metadata from ClickHouse, records the query in `knowledge_queries`, and assembles deterministic context packs.

## Knowledge Sources

- Markdown, text, and JSON files under `docs/knowledge`, `docs`, and `README.md`
- Incident rows and generated incident reports
- Anomaly events from Phase 4
- Topology snapshots from Phase 3

## Chunking Design

Chunking is deterministic and markdown-aware. The default chunk size is 1000 characters with 150 characters of overlap. Empty documents produce no chunks. Chunk IDs are stable hashes of document ID, chunk index, and chunk content.

## Metadata Design

Metadata includes `source_type`, `document_type`, `title`, `source_path`, `source_uri`, `phase`, `service`, `namespace`, `severity`, tags, content hash, and chunk hash. Path and text heuristics infer phase names, Online Boutique services, runbook/document types, and severity when explicit metadata is unavailable.

## Deterministic Embeddings

Phase 5 reuses `services/shared/embedding/deterministic.py`. It creates stable 128-dimension vectors through token hashing and normalization. This is a local placeholder suitable for repeatable development and tests; it can later be replaced by a real embedding model without changing the ClickHouse/Qdrant contract.

## ClickHouse Schema

Phase 5 adds:

- `knowledge_documents`
- `knowledge_chunks`
- `knowledge_ingestion_runs`
- `knowledge_queries`

All schema initialization is idempotent and preserves Phase 1-4 data.

## Qdrant Collection

Phase 5 adds Qdrant collection `cascade_knowledge_base` with vector size 128 and Cosine distance. The existing `cascade_incident_memory` collection remains unchanged.

## APIs

`knowledge-ingestion-service`:

- `GET /health`
- `GET /ready`
- `POST /ingest/docs`
- `POST /ingest/incidents`
- `POST /ingest/anomalies`
- `POST /ingest/topology`
- `POST /ingest/all`
- `GET /runs/recent`
- `GET /stats`

`knowledge-retrieval-service` and retrieval-service integration:

- `POST /knowledge/search`
- `POST /knowledge/context`
- `GET /knowledge/documents/recent`
- `GET /knowledge/chunks/recent`
- `GET /knowledge/stats`
- `GET /knowledge/runs/recent`

## Context Pack Format

Context packs include:

- query
- context_pack_id
- answer_mode
- sources
- evidence_chunks
- suggested_context_summary
- followup_questions
- confidence_hint
- limitations

The summary is deterministic and based only on retrieved chunks. When no chunks are found, the response says no relevant knowledge was found.

## Deployment Workflow

```powershell
.\scripts\deploy-phase-5.ps1
.\scripts\accept-phase-5.ps1
.\scripts\demo-phase-5.ps1
```

Use `.\scripts\reset-phase-5.ps1` to redeploy only Phase 5 resources. Add `-ClearPhase5Data` only when intentionally truncating Phase 5 tables and deleting the Phase 5 Qdrant collection.

## Acceptance Criteria

Acceptance verifies Phase 4 baseline services, Phase 5 tables, the Qdrant knowledge collection, both knowledge services, real ingestion into ClickHouse and Qdrant, source-grounded search/context APIs, and retrieval-service integration. It prints `PHASE 5 ACCEPTANCE: PASS` only when checks pass.

## Demo Workflow

The demo ingests docs/incidents/anomalies/topology, prints counts, searches operational knowledge, builds a context pack, and shows retrieval-service knowledge API integration.

## Troubleshooting

Run:

```powershell
.\scripts\debug-phase-5.ps1
```

It collects Kubernetes status, recent events, Phase 5 ClickHouse counts, Qdrant collection info, logs, health endpoints, recent runs, and a sample search.

## Known Limitations

- Deterministic local embeddings are placeholders.
- No LLM answer generation is included.
- No LangGraph agents are included.
- No autonomous reasoning is included.
- No remediation execution is included.
- No UI is included.
- Retrieval is source-grounded context assembly, not final agentic investigation.
