# Cascade

Cascade is a production-inspired local AI reliability platform for Kubernetes. It ingests telemetry, reconstructs incidents, detects anomalies, retrieves operational knowledge, runs deterministic investigations, plans safe chaos experiments, recommends remediation, and exposes the workflow through a Command Center UI.

It is designed to be runnable and reviewable in a local kind cluster without paid APIs, hosted services, GPUs, or real remediation enabled by default.

## Status

| Phase | Capability | Status |
| --- | --- | --- |
| 1 | Platform foundation | Complete |
| 2 | Telemetry, event backbone, incident intelligence | Complete |
| 3 | ClickHouse storage and Qdrant memory | Complete |
| 4 | ML-style anomaly detection | Complete |
| 5 | RAG and knowledge layer | Complete |
| 6 | Agent investigation runtime | Complete |
| 7 | Chaos automation with dry-run safety | Complete |
| 8 | Remediation and human approval | Complete |
| 9 | Command Center UI | Complete, gated by acceptance |
| 10 | Production hardening and final polish | Implemented locally |

## Architecture

Telemetry from the target Kubernetes workload flows into Redpanda, is enriched and archived into ClickHouse, indexed into Qdrant, and served through retrieval, agent, chaos, remediation, and Command Center APIs.

Core storage:

- Redpanda topics: `telemetry.raw`, `telemetry.enriched`, `experiments.events`, `anomalies.detected`, `agent.investigations`, `chaos.experiments`, `remediation.actions`
- ClickHouse database: `cascade`
- Qdrant collections: `cascade_incident_memory`, `cascade_knowledge_base`

See `docs/architecture/final-architecture.md`.

## Tech Stack

- Kubernetes and kind
- Redpanda Kafka-compatible event streaming
- ClickHouse analytical storage
- Qdrant vector search
- FastAPI Python services
- React/Vite Command Center
- PowerShell deployment, acceptance, backup, and debug tooling

## Quickstart

From `C:\Cascade`:

```powershell
.\scripts\deploy-phase-9.ps1
.\scripts\accept-phase-9.ps1
```

Open the Command Center:

```powershell
kubectl port-forward -n cascade-system svc/command-center 18300:8030
```

Then browse to `http://localhost:18300`.

## Full Local Validation

```powershell
.\scripts\accept-all.ps1
```

This runs Phase 2 through Phase 9 acceptance and writes logs under `run-output/`.

GitHub Actions validation runs on pull requests to `main`, pushes to `main`, and manual dispatch. It checks Python, PowerShell, frontend, Kubernetes YAML, secret hygiene, and representative Docker builds without deploying anywhere. See `docs/operations/ci-cd.md`.

Local pre-push CI mirror:

```powershell
pwsh ./scripts/ci-local.ps1 -SkipDockerBuild
```

Useful targeted commands:

```powershell
.\scripts\accept-phase-7.ps1 -DryRunOnly
.\scripts\demo-phase-9.ps1 -NoBrowser
.\scripts\debug-all.ps1
.\scripts\audit-secrets.ps1
```

## Operations

Backups:

```powershell
.\scripts\backup-clickhouse.ps1
.\scripts\backup-qdrant.ps1
```

List backups:

```powershell
.\scripts\list-clickhouse-backups.ps1
.\scripts\list-qdrant-backups.ps1
```

Restore scripts are dry-run by default and require `-ConfirmRestore`.

Runbooks:

- `docs/operations/runbook.md`
- `docs/operations/backups.md`
- `docs/operations/redpanda-recovery.md`
- `docs/operations/secret-hygiene.md`

## Safety Model

- Real remediation execution is disabled by default.
- The Command Center proxy blocks real remediation and real chaos execution by default.
- Phase 7 acceptance should use `-DryRunOnly` for normal local validation.
- Command Center API rate limiting is local and in-memory.
- `.env.example` contains placeholders only, and generated artifacts/backups/support bundles are ignored.

## Screenshots

Screenshots can be added under a tracked docs media path later. Generated screenshots and recordings are ignored by default to avoid committing bulky local artifacts.

## Limitations

Cascade is not a production deployment. The local kind setup is suitable for demos, development, and review. Production use would require authentication, distributed rate limiting, ingress/TLS, network policies, durable storage design, scheduled off-cluster backups, restore drills, Redpanda retention planning, and operational SLOs.

## Roadmap

- Production auth and RBAC
- Distributed API rate limiting
- CI-backed restore drills
- Hardened ingress and network policy
- Additional screenshots and demo recordings
