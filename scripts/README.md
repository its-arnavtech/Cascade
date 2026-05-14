# Cascade Scripts

## Normal Phase 2 Workflow

Use these for normal development and demos:

```powershell
.\scripts\deploy-phase-2.ps1
.\scripts\accept-phase-2.ps1
.\scripts\demo-phase-2.ps1
```

- `deploy-phase-2.ps1`: builds all Phase 2 service images, loads them into the `cascade` kind cluster, deploys Redpanda and all Phase 2 services, creates topics, and waits for rollouts.
- `accept-phase-2.ps1`: final Phase 2 acceptance gate. It verifies Online Boutique, Prometheus access, Redpanda topics, telemetry flow, experiment events, topology impact, causal reconstruction, and incident report generation.
- `demo-phase-2.ps1`: runs the end-to-end demo flow and prints a Markdown incident report. It uses `pod-kill-cartservice.yaml` when that Chaos Mesh manifest is present.
- `pod-kill-cartservice.yaml`: optional chaos smoke manifest used by the acceptance and demo scripts.

`PHASE 2 ACCEPTANCE: PASS` means Phase 2.1 still works, Redpanda is running as the Kafka-compatible broker, `telemetry.raw`, `telemetry.enriched`, and `experiments.events` all flow, and the experiment tracker, topology, causal reconstruction, and incident timeline services can generate a deterministic incident report.

## Normal Phase 3 Workflow

Use these after Phase 2 is available:

```powershell
.\scripts\deploy-phase-3.ps1
.\scripts\accept-phase-3.ps1
.\scripts\demo-phase-3.ps1
.\scripts\debug-phase-3.ps1
```

- `deploy-phase-3.ps1`: deploys the Phase 3 storage and memory layer. By default it first refreshes Phase 2, then builds and loads `telemetry-archiver`, `memory-indexer`, and `retrieval-service`, deploys ClickHouse and Qdrant, runs idempotent init jobs, and waits for rollouts.
- `accept-phase-3.ps1`: final Phase 3 acceptance gate. It verifies Phase 2 readiness, ClickHouse tables, Qdrant collection, real telemetry and experiment archival, incident/report persistence, memory indexing, and retrieval-service APIs.
- `demo-phase-3.ps1`: demonstrates storage and memory end to end by creating an experiment, persisting an incident/report, printing row and point counts, querying recent history, and running similar incident memory search.
- `reset-phase-3.ps1`: deletes and recreates only Phase 3 resources. It does not delete Online Boutique, Redpanda, or Phase 2 services. Use `-KeepData` to keep ClickHouse and Qdrant deployments.
- `debug-phase-3.ps1`: non-destructive diagnostics for Phase 3 resources, logs, Redpanda topics, ClickHouse counts, Qdrant collection state, and retrieval-service health.

`PHASE 3 ACCEPTANCE: PASS` means real Phase 2 data flowed into ClickHouse and Qdrant, incident/report persistence works, and retrieval-service can query stored telemetry, experiments, incidents, topology, and similar memories.

## Normal Phase 4 Workflow

Use these after Phase 3 is available:

```powershell
.\scripts\deploy-phase-4.ps1
.\scripts\accept-phase-4.ps1
.\scripts\demo-phase-4.ps1 -Synthetic
.\scripts\debug-phase-4.ps1
```

- `deploy-phase-4.ps1`: deploys the Phase 4 anomaly layer. By default it refreshes Phase 3, then builds and loads `feature-extractor-service`, `anomaly-detector-service`, and the updated `retrieval-service`, creates Phase 4 ClickHouse tables, ensures `anomalies.detected`, and waits for rollouts.
- `accept-phase-4.ps1`: final Phase 4 acceptance gate. It verifies Phase 3 readiness, Phase 4 schema, feature extraction, model status, anomaly detection, anomaly publishing, and retrieval anomaly APIs.
- `demo-phase-4.ps1`: demonstrates feature extraction, model status, anomaly detection, recent anomalies, and retrieval APIs. Use `-Synthetic` for a clearly labeled synthetic local anomaly demonstration.
- `reset-phase-4.ps1`: removes and redeploys only Phase 4 services. It does not delete Phase 1/2/3 infrastructure. Use `-ClearPhase4Tables` only when intentionally truncating Phase 4 ClickHouse tables.
- `debug-phase-4.ps1`: non-destructive diagnostics for Phase 4 service state, logs, ClickHouse counts, feature windows, anomaly rows, model runs, and health endpoints.

`PHASE 4 ACCEPTANCE: PASS` means real telemetry was transformed into feature windows, detector services scored those windows, a labeled anomaly path produced stored anomaly rows, `anomalies.detected` received valid JSON, and retrieval-service exposes Phase 4 query APIs.

## Normal Phase 5 Workflow

Use these after Phase 4 is available:

```powershell
.\scripts\deploy-phase-5.ps1
.\scripts\accept-phase-5.ps1
.\scripts\demo-phase-5.ps1
.\scripts\debug-phase-5.ps1
```

- `deploy-phase-5.ps1`: deploys the Phase 5 RAG + knowledge layer. By default it refreshes Phase 4, builds and loads `knowledge-ingestion-service`, `knowledge-retrieval-service`, and the updated `retrieval-service`, applies Phase 5 ClickHouse schema and Qdrant collection initialization, deploys services, and runs initial ingestion.
- `accept-phase-5.ps1`: final Phase 5 acceptance gate. It verifies Phase 4 baseline readiness, Phase 5 schema, `cascade_knowledge_base`, ingestion into ClickHouse and Qdrant, source-grounded knowledge search/context APIs, and retrieval-service knowledge integration.
- `demo-phase-5.ps1`: demonstrates docs/incidents/anomalies/topology ingestion, knowledge counts, source-grounded operational search, context pack assembly, and retrieval-service knowledge APIs.
- `reset-phase-5.ps1`: removes and redeploys only Phase 5 services. It does not delete Phase 1/2/3/4 infrastructure. Use `-ClearPhase5Data` only when intentionally truncating Phase 5 ClickHouse tables and deleting `cascade_knowledge_base`.
- `debug-phase-5.ps1`: non-destructive diagnostics for Phase 5 service state, logs, ClickHouse counts, Qdrant collection state, health endpoints, recent ingestion runs, and sample search output.

`PHASE 5 ACCEPTANCE: PASS` means operational docs, incident reports, anomaly events, and topology snapshots can be ingested into ClickHouse/Qdrant and retrieved as source-grounded evidence with citations and context packs.

## Normal Phase 6 Workflow

Use these after Phase 5 is available:

```powershell
.\scripts\deploy-phase-6.ps1
.\scripts\accept-phase-6.ps1
.\scripts\demo-phase-6.ps1
.\scripts\debug-phase-6.ps1
```

- `deploy-phase-6.ps1`: deploys the Phase 6 agent runtime. By default it refreshes Phase 5, builds and loads `agent-tool-gateway` and `agent-orchestrator-service`, applies Phase 6 ClickHouse schema and Redpanda topic initialization, deploys services, and waits for rollouts.
- `accept-phase-6.ps1`: final Phase 6 acceptance gate. It verifies Phase 5 baseline readiness, Phase 6 schema, `agent.investigations`, tool registry, representative tool calls, deterministic investigations, persisted run/step/tool/report rows, and text-only remediation boundaries.
- `demo-phase-6.ps1`: demonstrates the tool registry, deterministic agent status, evidence collection, tool-call trace, and final investigation report.
- `reset-phase-6.ps1`: removes and redeploys only Phase 6 services. It does not delete Phase 1/2/3/4/5 infrastructure. Use `-ClearPhase6Tables` only when intentionally truncating Phase 6 ClickHouse tables.
- `debug-phase-6.ps1`: non-destructive diagnostics for Phase 6 service state, logs, Redpanda topics, ClickHouse counts, health endpoints, tool registry, agent status, and recent investigations.

Phase 6 runs in deterministic local mode by default and does not require paid APIs, hosted LLMs, GPUs, or cloud services. Optional LangGraph/LLM configuration is documented in `docs/phase-6-agent-runtime.md`, but acceptance does not depend on it.

`PHASE 6 ACCEPTANCE: PASS` means the read-only tool gateway works, the deterministic investigation graph runs, evidence-backed reports are persisted, lifecycle events are available through `agent.investigations`, and suggested remediation remains text-only.

## Legacy And Recovery Scripts

These are intentionally kept because they are useful when the local kind cluster needs recovery or focused regression checks:

- `reset-to-phase-2-1.ps1`: removes active Phase 2 event-backbone resources and restores the stable Phase 2.1 observation-service baseline.
- `accept-phase-2-1.ps1`: regression test for the Phase 2.1 observation pipeline.
- `reset-phase-2-2-redpanda.ps1`: removes active Redpanda and stream-enricher resources while keeping source files intact, useful before a clean Redpanda redeploy.
- `debug-phase-2-2.ps1`: focused Redpanda, observation-service, and stream-enricher diagnostics for broker/topic/connectivity failures.
- `test-observation-service.ps1`: narrow observation-service endpoint smoke test referenced by the observation-service README.
- `debug-phase-3.ps1`: current Phase 3 diagnostics; prefer this for storage or memory issues.
- `debug-phase-4.ps1`: current Phase 4 diagnostics; prefer this for feature extraction or anomaly detection issues.
- `debug-phase-5.ps1`: current Phase 5 diagnostics; prefer this for knowledge ingestion or retrieval issues.
- `debug-phase-6.ps1`: current Phase 6 diagnostics; prefer this for agent runtime or tool gateway issues.

## Removed Obsolete Scripts And Docs

No active Phase 2-5 workflow scripts were removed in the pre-Phase-6 cleanup. One stale root planning note was removed because it had obsolete phase ordering, encoding artifacts, and no current references.

## Pre-Phase-7 Hygiene

Before beginning Phase 7, run the current acceptance gates in order:

```powershell
.\scripts\accept-phase-2.ps1
.\scripts\accept-phase-3.ps1
.\scripts\accept-phase-4.ps1
.\scripts\accept-phase-5.ps1
.\scripts\accept-phase-6.ps1
```

Local `.env` files, kubeconfigs, debug outputs, database volumes, generated reports, and model artifacts are intentionally ignored by the root `.gitignore`. Use `.env.example` for safe placeholder configuration only.

## Failure Triage

- Redpanda or topic failures: run `.\scripts\debug-phase-2-2.ps1`.
- Phase 2.1 regression: run `.\scripts\accept-phase-2-1.ps1`.
- Broken local cluster state: run `.\scripts\reset-to-phase-2-1.ps1`, then redeploy with `.\scripts\deploy-phase-2.ps1`.
- Phase 4 anomaly issue: run `.\scripts\debug-phase-4.ps1`.
- Phase 5 knowledge issue: run `.\scripts\debug-phase-5.ps1`.
- Phase 6 agent runtime issue: run `.\scripts\debug-phase-6.ps1`.
