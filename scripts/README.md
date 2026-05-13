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
```

- `deploy-phase-3.ps1`: deploys the Phase 3 storage and memory layer. By default it first refreshes Phase 2, then builds and loads `telemetry-archiver`, `memory-indexer`, and `retrieval-service`, deploys ClickHouse and Qdrant, runs idempotent init jobs, and waits for rollouts.
- `accept-phase-3.ps1`: final Phase 3 acceptance gate. It verifies Phase 2 readiness, ClickHouse tables, Qdrant collection, real telemetry and experiment archival, incident/report persistence, memory indexing, and retrieval-service APIs.
- `demo-phase-3.ps1`: demonstrates storage and memory end to end by creating an experiment, persisting an incident/report, printing row and point counts, querying recent history, and running similar incident memory search.
- `reset-phase-3.ps1`: deletes and recreates only Phase 3 resources. It does not delete Online Boutique, Redpanda, or Phase 2 services. Use `-KeepData` to keep ClickHouse and Qdrant deployments.
- `debug-phase-3.ps1`: non-destructive diagnostics for Phase 3 resources, logs, Redpanda topics, ClickHouse counts, Qdrant collection state, and retrieval-service health.

`PHASE 3 ACCEPTANCE: PASS` means real Phase 2 data flowed into ClickHouse and Qdrant, incident/report persistence works, and retrieval-service can query stored telemetry, experiments, incidents, topology, and similar memories.

## Legacy And Recovery Scripts

These are intentionally kept because they are useful when the local kind cluster needs recovery or focused regression checks:

- `reset-to-phase-2-1.ps1`: removes active Phase 2 event-backbone resources and restores the stable Phase 2.1 observation-service baseline.
- `accept-phase-2-1.ps1`: regression test for the Phase 2.1 observation pipeline.
- `reset-phase-2-2-redpanda.ps1`: removes active Redpanda and stream-enricher resources while keeping source files intact, useful before a clean Redpanda redeploy.
- `debug-phase-2-2.ps1`: focused Redpanda, observation-service, and stream-enricher diagnostics for broker/topic/connectivity failures.
- `test-observation-service.ps1`: narrow observation-service endpoint smoke test referenced by the observation-service README.
- `debug-phase-3.ps1`: current Phase 3 diagnostics; prefer this for storage or memory issues.

## Removed Obsolete Scripts

The old Apache Kafka-only helper scripts and the Phase 2.2-only acceptance gate were removed after the full Phase 2 gate passed. Use `accept-phase-2.ps1` for the current acceptance path.

## Failure Triage

- Redpanda or topic failures: run `.\scripts\debug-phase-2-2.ps1`.
- Phase 2.1 regression: run `.\scripts\accept-phase-2-1.ps1`.
- Broken local cluster state: run `.\scripts\reset-to-phase-2-1.ps1`, then redeploy with `.\scripts\deploy-phase-2.ps1`.
