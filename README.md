# CASCADE

Current project phase: Phase 6, the agent runtime.

Phase 1 status: complete.

Phase 2 status: complete. Redpanda-powered Kafka-compatible event backbone, observation pipeline, experiment tracking, topology, causal reconstruction, and incident report generation are implemented for local kind.

Phase 3 status: complete. ClickHouse analytical archival, Qdrant semantic memory, incident/report persistence, topology snapshots, and retrieval-service APIs are implemented for local kind.

Phase 4 status: complete. Feature extraction, explainable baseline anomaly detection, anomaly storage, Redpanda anomaly publishing, and retrieval anomaly APIs are implemented for local kind.

Phase 5 status: complete. Runbook/document ingestion, incident report ingestion, anomaly knowledge ingestion, topology knowledge ingestion, deterministic embeddings, ClickHouse knowledge metadata, Qdrant knowledge vectors, source-grounded search, context pack assembly, and retrieval-service knowledge APIs are implemented for local kind.

Phase 6 status: implemented. Read-only agent tool gateway, deterministic local investigation graph, evidence-backed report generation, investigation persistence, agent step/tool-call traceability, optional LangGraph/LLM hooks, and compact investigation lifecycle events are implemented for local kind.

## Phase 2 Quickstart

```powershell
.\scripts\deploy-phase-2.ps1
.\scripts\accept-phase-2.ps1
.\scripts\demo-phase-2.ps1
```

See `docs/phase-2.md` for architecture, services, topics, and acceptance details.

## Phase 3 Quickstart

```powershell
.\scripts\deploy-phase-3.ps1
.\scripts\accept-phase-3.ps1
.\scripts\demo-phase-3.ps1
```

See `docs/phase-3-storage-memory.md` for storage schemas, memory design, retrieval APIs, acceptance, and troubleshooting.

## Phase 4 Quickstart

```powershell
.\scripts\deploy-phase-4.ps1
.\scripts\accept-phase-4.ps1
.\scripts\demo-phase-4.ps1 -Synthetic
```

See `docs/phase-4-anomaly-detection.md` for feature extraction, model design, anomaly schemas, acceptance, and troubleshooting.

## Phase 5 Quickstart

```powershell
.\scripts\deploy-phase-5.ps1
.\scripts\accept-phase-5.ps1
.\scripts\demo-phase-5.ps1
```

See `docs/phase-5-rag-knowledge-layer.md` for knowledge ingestion, retrieval APIs, context pack format, acceptance, and troubleshooting.

## Phase 6 Quickstart

```powershell
.\scripts\deploy-phase-6.ps1
.\scripts\accept-phase-6.ps1
.\scripts\demo-phase-6.ps1
```

See `docs/phase-6-agent-runtime.md` for the tool gateway, investigation graph, deterministic mode, APIs, safety boundaries, acceptance, and troubleshooting.

## Phase 3 - Storage + Memory Layer

Phase 3 adds durable storage and memory to the completed Phase 2 incident-intelligence pipeline:

- ClickHouse telemetry, time-series, and event analytics
- Qdrant vector memory in `cascade_incident_memory`
- telemetry and experiment archival from Redpanda
- incident and report persistence
- topology snapshot persistence
- deterministic semantic memory indexing
- similarity search for past incidents
- retrieval-service APIs over ClickHouse and Qdrant

```text
Prometheus
-> observation-service
-> telemetry.raw
-> Redpanda
-> stream-enricher
-> telemetry.enriched
-> telemetry-archiver
-> ClickHouse

Chaos Mesh
-> experiment-tracker-service
-> experiments.events
-> telemetry-archiver
-> ClickHouse

causal-reconstruction-service + incident-timeline-service
-> retrieval-service incident/report archival
-> ClickHouse + Qdrant
```

## Phase 4 - ML Anomaly Detection

Phase 4 moves Cascade from remembering incidents to detecting abnormal service behavior automatically:

- feature extraction from ClickHouse `telemetry_events`
- service/workload feature windows in `telemetry_feature_windows`
- rolling z-score, threshold baseline, and optional Isolation Forest detectors
- ensemble risk score and severity mapping
- anomaly persistence in ClickHouse `anomaly_events`
- detector execution tracking in `model_runs`
- Redpanda publishing to `anomalies.detected`
- retrieval-service anomaly APIs

```text
ClickHouse telemetry_events
-> feature-extractor-service
-> telemetry_feature_windows
-> anomaly-detector-service
-> anomaly_events
-> anomalies.detected
-> retrieval-service anomaly APIs
```

## Phase 5 - RAG + Knowledge Layer

Phase 5 lets Cascade retrieve source-grounded operational knowledge without requiring OpenAI, hosted inference, model downloads, LangGraph, autonomous agents, remediation execution, or a UI.

- runbook and document ingestion
- incident report ingestion
- anomaly knowledge ingestion
- topology knowledge ingestion
- deterministic local 128-dimension embeddings
- ClickHouse `knowledge_documents`, `knowledge_chunks`, `knowledge_ingestion_runs`, and `knowledge_queries`
- Qdrant `cascade_knowledge_base`
- source-grounded operational search
- deterministic context pack assembly
- retrieval-service `/knowledge/*` APIs

```text
docs/runbooks/incidents/anomalies/topology
-> knowledge-ingestion-service
-> knowledge_documents / knowledge_chunks
-> Qdrant cascade_knowledge_base
-> knowledge-retrieval-service
-> retrieval-service knowledge APIs
```

## Phase 6 - LangChain/LangGraph Agent Runtime

Phase 6 lets Cascade investigate incidents and anomalies by calling real platform tools and assembling evidence-backed reports. It runs without paid APIs by default.

- `agent-tool-gateway` wraps existing Cascade APIs as read-only tools.
- `agent-orchestrator-service` runs graph-style investigation workflows.
- deterministic local planner mode is the default acceptance/demo mode.
- optional LangGraph/LLM configuration hooks are present but not required.
- ClickHouse stores `investigation_runs`, `agent_steps`, `agent_tool_calls`, and `investigation_reports`.
- Redpanda topic `agent.investigations` stores compact lifecycle events.
- reports include evidence refs, confidence, limitations, recommended next investigation steps, and text-only remediation suggestions.
- Phase 6 does not execute remediation, mutate Kubernetes resources, run chaos experiments, or provide a UI.

```text
anomaly_events / incidents / telemetry / topology / knowledge
-> agent-tool-gateway
-> agent-orchestrator-service
-> investigation_runs / agent_steps / investigation_reports
-> agent.investigations
```

## Current Stack

- Docker Desktop
- kind Kubernetes cluster
- kubectl
- PowerShell
- Python
- FastAPI
- aiokafka
- Redpanda Kafka-compatible broker
- Prometheus
- Grafana
- OpenTelemetry
- Chaos Mesh
- ClickHouse
- Qdrant
- Google Online Boutique target app

## Repository Hygiene

- Secrets and environment-specific values must use local environment variables or an untracked `.env` file.
- `.env`, kubeconfig files, local database volumes, debug/demo/acceptance outputs, generated reports, and model artifacts are ignored.
- Use `.env.example` for safe placeholder configuration.
- Do not commit local Kubernetes configs, ClickHouse/Qdrant/Redpanda data directories, or exported telemetry/incident dumps.

## Remaining Roadmap

### Phase 7 - Chaos Engineering Automation

Goal: close the loop with controlled failure injection, blast-radius controls, resilience scoring, and safe experiment execution.

### Phase 8 - Remediation + Human Approval

Goal: generate safe evidence-backed remediation plans with human approval and gated execution.

### Phase 9 - UI / Command Center

Goal: make Cascade visually demoable and operationally usable with topology, telemetry, incident, agent, chaos, and remediation views.

### Phase 10 - Production Hardening

Goal: add auth/RBAC, improved docs, architecture diagrams, one-command demo, CI, screenshots/GIFs/video, and final portfolio polish.

## Author

Built as a high-complexity systems + AI project targeting SWE, Platform Engineering, and ML Infrastructure roles.

## License

MIT
