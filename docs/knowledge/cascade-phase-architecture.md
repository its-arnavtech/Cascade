# Cascade Phase Architecture

Cascade is a Kubernetes-native distributed systems and AI infrastructure platform for observing failures, reconstructing incidents, storing operational memory, detecting anomalies, and retrieving source-grounded knowledge.

## Phase 1-2 Event Pipeline

Prometheus and target workload signals flow through `observation-service` into Redpanda topic `telemetry.raw`. `stream-enricher` enriches events into `telemetry.enriched`. Chaos Mesh experiment metadata flows through `experiment-tracker-service` into `experiments.events`.

## Phase 3 Storage And Memory

`telemetry-archiver` writes telemetry and experiment events into ClickHouse. `topology-service`, `causal-reconstruction-service`, and `incident-timeline-service` create topology snapshots, incidents, and reports. `retrieval-service` stores incident memory in Qdrant collection `cascade_incident_memory`.

## Phase 4 Anomaly Detection

`feature-extractor-service` reads ClickHouse `telemetry_events` and writes `telemetry_feature_windows`. `anomaly-detector-service` scores feature windows, writes `anomaly_events` and `model_runs`, and publishes `anomalies.detected`.

## Phase 5 Knowledge Layer

`knowledge-ingestion-service` ingests runbooks, README/docs, incident reports, anomaly records, and topology snapshots. It chunks content, creates deterministic 128-dimension embeddings, stores metadata in ClickHouse `knowledge_documents` and `knowledge_chunks`, and indexes vectors in Qdrant collection `cascade_knowledge_base`.

`knowledge-retrieval-service` performs source-grounded search and assembles context packs. It does not call an LLM, run LangGraph, execute remediation, or make unsupported root-cause claims.
