# Cascade

Cascade is a Kubernetes-native AI reliability command center that observes services, detects anomalies, retrieves operational knowledge, runs deterministic investigations, and recommends safe remediation workflows with human approval and dry-run validation.

It is a local, production-inspired MVP for demonstrating how telemetry, incidents, runbooks, topology, safety policy, and operator workflows can be connected inside a Kubernetes reliability platform.

## What It Does

Cascade turns raw service signals into an operator-facing reliability workflow:

- Watches a demo Kubernetes workload and collects telemetry.
- Streams raw and enriched events through Kafka-compatible topics.
- Archives telemetry, incidents, feature windows, anomaly events, investigations, chaos runs, and remediation records.
- Builds semantic memory and source-grounded operational knowledge.
- Extracts features and detects anomaly signals.
- Runs deterministic, read-only agent investigations.
- Plans chaos experiments with safety policy checks and dry-run execution.
- Generates remediation recommendations with approval records.
- Validates remediation plans through dry-run workflows.
- Presents the system through the Command Center web UI.

## Quick Start

From the repository root:

```powershell
cd C:\Cascade

.\scripts\deploy-phase-9.ps1
.\scripts\accept-phase-9.ps1
```

Open the Command Center:

```powershell
kubectl port-forward -n cascade-system svc/command-center 18300:8030
```

Then browse to:

```text
http://localhost:18300
```

## Why It Exists

Modern distributed systems generate too much telemetry and too many failure signals for humans to manually connect in real time. Cascade explores a practical reliability workflow where telemetry, anomalies, runbooks, incident history, topology, and safety policies are stitched together into a single SRE command surface.

The goal is not autonomous production control. The goal is safer operator assistance: evidence gathering, context retrieval, deterministic investigation, human approval, and dry-run validation before any dangerous action is considered.

## Current Status

Cascade currently runs as a local kind-based MVP/demo platform.

- The Command Center UI is available locally after deployment.
- Phase 2 through Phase 9 acceptance scripts validate the current local system.
- Dangerous real execution is disabled by default.
- Chaos and remediation workflows support planning, approval records, and dry-run validation.
- The system is not production-hardened SaaS. Production use would require additional authentication, authorization, ingress/TLS, network policy, durable storage, backup/restore drills, observability hardening, and operational SLOs.

## Architecture Overview

High-level flow:

```text
Online Boutique target workload
  -> observation-service / telemetry collection
  -> Redpanda topics
  -> stream enrichment and archival
  -> ClickHouse + Qdrant
  -> feature extraction and anomaly detection
  -> retrieval and knowledge services
  -> agent tool gateway and orchestrator
  -> chaos and remediation services
  -> command-center-api
  -> Command Center UI
```

Primary namespaces:

- `cascade-system`: Cascade platform services and data infrastructure.
- `cascade-targets`: Online Boutique target workload.
- `monitoring`: Prometheus stack used by observation services.

Core storage and event backbone:

- Redpanda topics include `telemetry.raw`, `telemetry.enriched`, `experiments.events`, `anomalies.detected`, `agent.investigations`, `chaos.experiments`, and `remediation.actions`.
- ClickHouse database: `cascade`.
- Qdrant collections include incident memory and the knowledge base.

## Major Components

### Target Workload

- Online Boutique services run in `cascade-targets`.
- Cascade observes this workload as the local demo application.

### Telemetry and Streaming

- `observation-service`: collects workload telemetry from Prometheus.
- `stream-enricher`: normalizes and enriches telemetry events.
- Redpanda: Kafka-compatible event backbone.

### Storage and Memory

- ClickHouse: analytical storage for telemetry, incidents, anomaly records, investigations, chaos runs, and remediation records.
- Qdrant: vector storage for incident memory and source-grounded knowledge retrieval.
- `telemetry-archiver`: persists streamed telemetry and related records.
- `memory-indexer`: indexes records into semantic memory.

### Detection and Knowledge

- `feature-extractor-service`: builds telemetry feature windows.
- `anomaly-detector-service`: scores feature windows and records anomaly events.
- `knowledge-ingestion-service`: ingests repository knowledge into searchable chunks.
- `knowledge-retrieval-service`: returns source-grounded context and evidence.
- `retrieval-service`: provides query APIs over stored telemetry, incidents, anomalies, knowledge stats, and related records.

### Agent Runtime

- `agent-tool-gateway`: exposes safe, read-only tools for investigation workflows.
- `agent-orchestrator-service`: runs deterministic investigation flows and records evidence.

### Chaos and Remediation

- `chaos-planner-service`: creates safety-checked chaos plans.
- `chaos-executor-service`: supports dry-run chaos execution and blocks real execution by default.
- `remediation-recommender-service`: creates remediation plans from incidents, investigations, or manual objectives.
- `approval-service`: records human approval and rejection decisions.
- `remediation-executor-service`: supports dry-run validation and blocks real execution by default.

### UI

- `command-center`: React/Vite frontend served by nginx.
- `command-center-api`: FastAPI proxy/BFF that exposes the platform APIs to the UI and enforces safety boundaries.

## Tech Stack

Frontend:

- React
- TypeScript
- Vite
- TanStack Query
- `lucide-react`
- nginx static serving

Backend:

- Python
- FastAPI
- Pydantic
- Service-oriented microservices

Data and infrastructure:

- Kubernetes
- kind
- Docker
- Redpanda / Kafka-compatible topics
- ClickHouse
- Qdrant
- Prometheus
- PowerShell automation scripts

Testing and quality:

- pytest
- unittest
- Ruff
- TypeScript build/typecheck
- Vite production build
- PowerShell acceptance scripts
- Kubernetes manifest validation
- Docker build smoke tests

## Prerequisites

For local development on Windows:

- Windows PowerShell
- Docker Desktop
- kind
- kubectl
- Node.js and npm compatible with the Command Center frontend
- Python

Exact tool versions are intentionally not hardcoded here. Check the relevant package files, lockfiles, Dockerfiles, and CI workflow when version precision matters.

## Command Center Development

The UI source lives in `web/command-center`.

Useful frontend commands:

```powershell
cd C:\Cascade\web\command-center

npm install
npm run typecheck
npm run build
npm run dev
```

The local Vite dev server is useful for frontend iteration. The Kubernetes-hosted product UI is served by the `command-center` deployment through nginx.

## Validation

Run targeted Phase 9 validation:

```powershell
cd C:\Cascade

.\scripts\accept-phase-9.ps1
```

Run the broader local acceptance suite:

```powershell
.\scripts\accept-all.ps1
```

Run the local CI mirror:

```powershell
.\scripts\ci-local.ps1
```

Useful focused checks:

```powershell
.\scripts\audit-secrets.ps1
.\scripts\accept-phase-7.ps1 -DryRunOnly
.\scripts\demo-phase-9.ps1 -NoBrowser
.\scripts\debug-all.ps1
```

Acceptance and debug scripts may write logs under ignored output directories such as `run-output/`. Do not commit generated logs, bundles, backups, or support artifacts.

## Safety Boundaries

Cascade is safety-first by default:

- Real chaos execution is blocked by default.
- Real remediation execution is blocked by default.
- Dry-run chaos execution is allowed.
- Remediation planning, approval records, and dry-run validation are allowed.
- The Command Center API proxy blocks real dangerous execution paths by default.
- Agent tools are designed around deterministic, read-only investigation workflows.
- No arbitrary command execution should be exposed through the UI.

Do not commit secrets, tokens, kubeconfigs, database credentials, private keys, generated `.env` files, or real API keys. `.env.example` is for placeholders only.

## Useful Scripts

Deployment:

```powershell
.\scripts\deploy-phase-9.ps1
```

Acceptance:

```powershell
.\scripts\accept-phase-9.ps1
.\scripts\accept-all.ps1
```

Debugging:

```powershell
.\scripts\debug-phase-9.ps1
.\scripts\debug-all.ps1
```

Demo:

```powershell
.\scripts\demo-phase-9.ps1 -NoBrowser
```

Secret hygiene:

```powershell
.\scripts\audit-secrets.ps1
```

Backups:

```powershell
.\scripts\backup-clickhouse.ps1
.\scripts\backup-qdrant.ps1
.\scripts\list-clickhouse-backups.ps1
.\scripts\list-qdrant-backups.ps1
```

Restore scripts are dry-run oriented and require explicit confirmation flags before performing restore operations.

## Repository Map

```text
docs/                         Architecture and operations notes
infra/kubernetes/             Kubernetes manifests
scripts/                      Deployment, acceptance, debug, backup, and CI helpers
services/                     FastAPI platform services
targets/online-boutique-src/  Demo target workload
tests/                        Python unit and integration-oriented tests
web/command-center/           Command Center frontend
```

## Current Limitations

Cascade is a local demo/MVP platform, not a hardened production service.

Known areas that would need production work include:

- Authentication and RBAC.
- Ingress, TLS, and identity-aware access.
- Network policies and workload isolation.
- Durable storage configuration and capacity planning.
- Distributed rate limiting.
- Off-cluster backup and restore automation.
- Restore drills and disaster recovery procedures.
- Redpanda retention and operational tuning.
- Production-grade observability and alerting.
- Security review for all operator-facing workflows.

## More Documentation

Useful starting points:

- `docs/architecture/final-architecture.md`
- `docs/operations/ci-cd.md`
- `docs/operations/runbook.md`
- `docs/operations/backups.md`
- `docs/operations/secret-hygiene.md`
