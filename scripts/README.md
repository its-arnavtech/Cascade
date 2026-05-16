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

## Normal Phase 7 Workflow

Use these after Phase 6 is available:

```powershell
.\scripts\deploy-phase-7.ps1
.\scripts\accept-phase-7.ps1
.\scripts\demo-phase-7.ps1
.\scripts\debug-phase-7.ps1
```

- `deploy-phase-7.ps1`: deploys the Phase 7 chaos automation layer. By default it refreshes Phase 6, verifies Chaos Mesh CRDs, builds and loads `chaos-planner-service`, `chaos-executor-service`, and the updated `agent-tool-gateway`, applies Phase 7 ClickHouse schema and Redpanda topic initialization, deploys RBAC/services, and waits for rollouts.
- `accept-phase-7.ps1`: final Phase 7 acceptance gate. It verifies Phase 6 readiness, Chaos Mesh CRDs, Phase 7 schema/topic, service readiness, safety rejection, dry-run execution, optional real bounded pod-kill execution, cleanup, observations, resilience scores, and chaos lifecycle events.
- `demo-phase-7.ps1`: demonstrates safety policy, safe plan creation, safety rejection, dry-run execution, optional real pod-kill execution, observation, resilience scoring, and optional agent investigation.
- `reset-phase-7.ps1`: cleans up Cascade-managed Chaos Mesh resources and redeploys only Phase 7 services. It does not delete Phase 1/2/3/4/5/6 infrastructure. Use `-ClearPhase7Tables` only when intentionally truncating Phase 7 ClickHouse tables.
- `debug-phase-7.ps1`: non-destructive diagnostics for Phase 7 services, RBAC-adjacent state, Chaos Mesh resources, ClickHouse counts, Redpanda topics, logs, policy, plans, runs, and scores.

Non-disruptive validation:

```powershell
.\scripts\accept-phase-7.ps1 -DryRunOnly
.\scripts\demo-phase-7.ps1 -DryRunOnly
```

Phase 7 safety boundaries:

- chaos is allowlisted to `cascade-targets` by default.
- system namespaces and `cascade-system` are denied.
- real execution requires `approved=true`.
- generated Chaos Mesh resources carry Cascade cleanup labels.
- executor RBAC cannot mutate deployments, services, configmaps, secrets, or remediation resources.
- suggested remediation remains text only.

`PHASE 7 ACCEPTANCE: PASS` means the planner can create safe plans, unsafe plans are rejected, dry-runs do not create Chaos Mesh resources, real bounded chaos works when enabled, cleanup is verified, observations/scores are persisted, and `chaos.experiments` contains lifecycle events.

## Normal Phase 8 Workflow

Use these after Phase 7 is available:

```powershell
.\scripts\deploy-phase-8.ps1
.\scripts\accept-phase-8.ps1
.\scripts\demo-phase-8.ps1
.\scripts\debug-phase-8.ps1
```

- `deploy-phase-8.ps1`: deploys the remediation and human approval layer. By default it refreshes Phase 7, builds and loads `remediation-recommender-service`, `approval-service`, `remediation-executor-service`, and the updated `agent-tool-gateway`, applies Phase 8 ClickHouse schema and Redpanda topic initialization, deploys RBAC/services, and waits for rollouts.
- `accept-phase-8.ps1`: final Phase 8 acceptance gate. It verifies Phase 7 readiness, Phase 8 schema/topic, service readiness, plan generation, safety rejection, approval/rejection records, dry-run validation, real execution disabled by default, and read-only agent gateway tools.
- `demo-phase-8.ps1`: demonstrates plan generation, evidence/rollback steps, safety policy, unsafe rejection, approval, dry-run validation, real execution blocking, and read-only agent tools.
- `reset-phase-8.ps1`: removes and redeploys only Phase 8 resources. It does not delete Phase 1/2/3/4/5/6/7 infrastructure. Use `-ClearPhase8Tables` only when intentionally truncating Phase 8 ClickHouse tables.
- `debug-phase-8.ps1`: non-destructive diagnostics for Phase 8 services, RBAC-adjacent state, Redpanda topics, ClickHouse counts, logs, policy, plans, approvals, and executions.

Phase 8 safety boundaries:

- recommendations are deterministic and evidence-backed.
- rollback/runbook steps are required before executable actions.
- approvals and rejections are explicit audit records.
- default workflows are dry-run only and do not mutate workloads.
- `EXECUTION_ENABLED=false` by default blocks real execution.
- denied namespaces include `kube-system`, `monitoring`, `cascade-system`, `default`, and storage/system namespaces.
- agent tools are read-only; agents cannot approve or execute remediation.

`PHASE 8 ACCEPTANCE: PASS` means safe plans can be generated, unsafe plans are rejected, approvals are stored, dry-run execution records are persisted with `executed=false`, real execution is blocked by default, and `remediation.actions` exists for lifecycle events.

## Normal Phase 9 Workflow

Use these after Phase 8 is available:

```powershell
.\scripts\deploy-phase-9.ps1
.\scripts\accept-phase-9.ps1
.\scripts\demo-phase-9.ps1
.\scripts\debug-phase-9.ps1
```

- `deploy-phase-9.ps1`: builds the React command center and FastAPI BFF images, loads them into kind, deploys `command-center-api` and `command-center`, and waits for rollouts.
- `accept-phase-9.ps1`: final Phase 9 acceptance gate. It verifies Phase 8 baseline resources, UI deployments/endpoints, static assets, API proxy routes, safe investigation/remediation/chaos dry-run actions, and frontend build.
- `demo-phase-9.ps1`: port-forwards the UI, prints API health/counts, optionally runs a safe investigation and remediation dry-run demo, and prints browser routes.
- `reset-phase-9.ps1`: deletes and redeploys only Phase 9 resources. It does not delete Phase 1-8 services, Online Boutique, Redpanda, ClickHouse, or Qdrant.
- `debug-phase-9.ps1`: non-destructive diagnostics for command-center resources, logs, health endpoints, API samples, and local port-forward instructions.

Local UI access:

```powershell
kubectl port-forward -n cascade-system svc/command-center 18300:8030
```

Open `http://localhost:18300`.

Phase 9 safety boundaries:

- the UI calls real Cascade APIs through `/api/*`.
- real remediation execution is disabled by default and blocked by the BFF.
- real chaos execution controls are not exposed by default.
- supported mutations are safe operator workflows: investigations, plan creation, approval/rejection records, and dry-run validation.

`PHASE 9 ACCEPTANCE: PASS` means the browser entrypoint, API proxy, dashboard data, health checks, safe investigation creation, chaos dry-run planning/execution, remediation plan/approval/dry-run workflow, and frontend build are working.

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
- `debug-phase-7.ps1`: current Phase 7 diagnostics; prefer this for chaos planning, execution, cleanup, or scoring issues.
- `debug-phase-8.ps1`: current Phase 8 diagnostics; prefer this for remediation plans, approvals, dry-run validation, or safety policy issues.
- `debug-phase-9.ps1`: current Phase 9 diagnostics; prefer this for command-center UI or API proxy issues.

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
.\scripts\accept-phase-7.ps1 -DryRunOnly
.\scripts\accept-phase-8.ps1
.\scripts\accept-phase-9.ps1
```

Local `.env` files, kubeconfigs, debug outputs, database volumes, generated reports, and model artifacts are intentionally ignored by the root `.gitignore`. Use `.env.example` for safe placeholder configuration only.

## Failure Triage

- Redpanda or topic failures: run `.\scripts\debug-phase-2-2.ps1`.
- Phase 2.1 regression: run `.\scripts\accept-phase-2-1.ps1`.
- Broken local cluster state: run `.\scripts\reset-to-phase-2-1.ps1`, then redeploy with `.\scripts\deploy-phase-2.ps1`.
- Phase 4 anomaly issue: run `.\scripts\debug-phase-4.ps1`.
- Phase 5 knowledge issue: run `.\scripts\debug-phase-5.ps1`.
- Phase 6 agent runtime issue: run `.\scripts\debug-phase-6.ps1`.
- Phase 7 chaos automation issue: run `.\scripts\debug-phase-7.ps1`.
- Phase 8 remediation approval issue: run `.\scripts\debug-phase-8.ps1`.
- Phase 9 command center issue: run `.\scripts\debug-phase-9.ps1`.

## Phase 10 Final Hardening Scripts

- `accept-all.ps1`: runs Phase 2 through Phase 9 acceptance, writes logs under `run-output/accept-all-<timestamp>/`, stops on first failure unless `-ContinueOnFailure` is provided, and supports `-SkipPhase9`.
- `debug-all.ps1`: collects a local support bundle under `support-bundles/<timestamp>/` with Kubernetes state, events, logs, Redpanda topics, ClickHouse counts, Qdrant collection info, health checks, and Command Center status.
- `audit-secrets.ps1`: scans tracked files for suspicious secret-like keys without printing values. It exits nonzero on high-confidence non-placeholder assignments.
- `ensure-redpanda-topics.ps1`: idempotently ensures the required Cascade Redpanda topics exist.
- `backup-clickhouse.ps1`, `list-clickhouse-backups.ps1`, `restore-clickhouse.ps1`: local ClickHouse backup/list/restore helpers. Restore is dry-run by default and requires `-ConfirmRestore`.
- `backup-qdrant.ps1`, `list-qdrant-backups.ps1`, `restore-qdrant.ps1`: local Qdrant snapshot/list/restore helpers. Restore is dry-run by default and requires `-ConfirmRestore`.
- `ci-local.ps1`: runs the main CI validation checks locally before pushing, without requiring Kubernetes by default.

Safe flags and defaults:

- `-DryRunOnly` keeps Phase 7 validation from creating real chaos.
- `-NoBrowser` keeps demo scripts from opening a browser.
- `-ConfirmRestore` is required for restore mutation.
- `-SkipDockerBuild` skips local Docker smoke builds in `ci-local.ps1`.
- Real remediation execution remains disabled by default through `EXECUTION_ENABLED=false`.
- Real chaos and real remediation routes remain blocked through the Command Center proxy unless explicitly reconfigured.
