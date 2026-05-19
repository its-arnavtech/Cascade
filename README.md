# Cascade

Cascade is a Kubernetes-native AI reliability command center that observes an authorized target workload, builds topology, collects telemetry, detects abnormal behavior, predicts blast radius, ranks likely causes, and recommends policy-gated remediation with human approval and dry-run validation.

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

## Quick Demo With Sock Shop

From the repository root:

```powershell
cd C:\Cascade

.\scripts\deploy.ps1
.\scripts\deploy-targets.ps1
.\scripts\ensure-redpanda-topics.ps1
.\scripts\accept.ps1
```

Open the Command Center using:

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

## Bring Your Own Target Workload

Sock Shop remains the canonical demo, but external users can connect their own Kubernetes app as an additional target path.

Safe local/dev/staging flow:

```powershell
cd C:\Cascade

.\scripts\deploy.ps1

kubectl create namespace cascade-targets --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace cascade-targets cascade.io/monitored=true --overwrite
kubectl apply -n cascade-targets -f path\to\your-app.yaml

.\scripts\validate-target.ps1 -Namespace cascade-targets -ExpectedServices frontend,api -ShowLabels
```

Describe the app with a target config:

```powershell
Copy-Item -Recurse targets\template targets\my-app
notepad targets\my-app\target.yaml

.\scripts\validate-target.ps1 -Namespace cascade-targets -TargetConfig targets\my-app\target.yaml -Strict
.\scripts\configure-target.ps1 -TargetConfig targets\my-app\target.yaml
.\scripts\ensure-redpanda-topics.ps1
.\scripts\accept-telemetry.ps1
```

Open the Command Center:

```powershell
kubectl port-forward -n cascade-system svc/command-center 18300:8030
```

Then browse to `http://localhost:18300`.

The target config fields are `name`, `namespace`, `frontend_service`, `services`, `dependency_edges`, `safe_chaos_services`, `protected_services`, and `load_generator`. Use `protected_services` for databases, brokers, caches, queues, auth stores, and stateful services. Use `safe_chaos_services` only for stateless services you own and are willing to test.

Dry-run remains the default. Optional live chaos engineering and remediation demos are explicit local-kind flows only:

```powershell
.\scripts\install-chaos-mesh.ps1 -ConfirmLocalKind
.\scripts\verify-chaos-mesh.ps1
.\scripts\demo-real-chaos.ps1 -ConfirmLocalKind
.\scripts\demo-real-remediation.ps1 -ConfirmLocalKind
```

Do not run live controlled failure injection or live remediation against production.

## Current Status

Cascade currently runs as a local kind-based MVP/demo platform.

- The Command Center UI is available locally after deployment.
- Acceptance scripts validate the current local system end to end.
- Dangerous real execution is disabled by default.
- Chaos and remediation workflows support planning, approval records, and dry-run validation.
- The system is not production-hardened SaaS. Production use would require additional authentication, authorization, ingress/TLS, network policy, durable storage, backup/restore drills, observability hardening, and operational SLOs.

## Architecture Overview

High-level flow:

```text
Sock Shop target workload
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
- `cascade-targets`: Sock Shop target workload.
- `monitoring`: Prometheus stack used by observation services.

Core storage and event backbone:

- Redpanda topics include `telemetry.raw`, `telemetry.enriched`, `experiments.events`, `anomalies.detected`, `agent.investigations`, `chaos.experiments`, and `remediation.actions`.
- ClickHouse database: `cascade`.
- Qdrant collections include incident memory and the knowledge base.

## Major Components

### Target Workload

- Sock Shop services run in `cascade-targets`.
- Cascade observes this workload as the local demo application.

### Telemetry Pipeline

- `observation-service`: collects workload telemetry from Prometheus.
- `stream-enricher`: normalizes and enriches telemetry events.
- Redpanda: Kafka-compatible event backbone.

### Storage and Memory

- ClickHouse: analytical storage for telemetry, incidents, anomaly records, investigations, chaos runs, and remediation records.
- Qdrant: vector storage for incident memory and source-grounded knowledge retrieval.
- `telemetry-archiver`: persists streamed telemetry and related records.
- `memory-indexer`: indexes records into semantic memory.

### Anomaly Detection

- `feature-extractor-service`: builds telemetry feature windows.
- `anomaly-detector-service`: scores feature windows and records anomaly events.

### Knowledge and RAG

- `knowledge-ingestion-service`: ingests repository knowledge into searchable chunks.
- `knowledge-retrieval-service`: returns source-grounded context and evidence.
- `retrieval-service`: provides query APIs over stored telemetry, incidents, anomalies, knowledge stats, and related records.

### Agent Investigations

- `agent-tool-gateway`: exposes safe, read-only tools for investigation workflows.
- `agent-orchestrator-service`: runs deterministic investigation flows and records evidence.

### Chaos Engineering

- `chaos-planner-service`: creates safety-checked chaos plans.
- `chaos-executor-service`: supports dry-run chaos execution and blocks real execution by default.

### Remediation

- `remediation-recommender-service`: creates remediation plans from incidents, investigations, or manual objectives.
- `approval-service`: records human approval and rejection decisions.
- `remediation-executor-service`: supports dry-run validation and blocks real execution by default.

### Command Center UI

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

Run targeted Command Center UI validation:

```powershell
cd C:\Cascade

.\scripts\accept.ps1
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
.\scripts\validate-target.ps1 -Namespace cascade-targets
.\scripts\accept-chaos.ps1 -DryRunOnly
.\scripts\demo.ps1 -NoBrowser
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

## Command Center UI Modes

Dry-run UI mode is the default and is safe for normal testers. The Command Center lets testers inspect topology, telemetry trends, chaos plans, remediation plans, approvals, and dry-run validation without mutating the cluster.

Local live-demo UI mode is optional and local-kind only. It requires executor live-demo flags and the Command Center proxy dangerous-action flag before the browser exposes bounded real actions. Even then, the backend remains the final enforcement layer: approvals, dry-run-first checks, rollback and post-check requirements, protected-service checks, namespace allowlists, and wildcard-selector rejection still run server-side. The UI only exposes `pod_kill` for chaos and `restart_deployment` for remediation against allowlisted `cascade-targets` services.

To exercise live mode through scripts:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo-real-chaos.ps1 -ConfirmLocalKind
powershell -ExecutionPolicy Bypass -File .\scripts\demo-real-remediation.ps1 -ConfirmLocalKind
```

For a browser live-demo path, use the explicit UI toggle script. It verifies the local `kind-cascade` context and `cascade-targets` namespace, enables only the required executor and proxy flags, waits for rollouts, and prints `/api/live-demo/status`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\enable-ui-live-demo.ps1 -ConfirmLocalKind
```

Disable UI live-demo mode immediately after a local demo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\disable-ui-live-demo.ps1
```

This does not imply production readiness.

## Testing Real Chaos And Remediation Locally

Dry-run is the default. Real actions are available only through opt-in local demo scripts or local live-demo UI mode, not through normal deployment.

Prerequisites:

- local kind context `kind-cascade`
- Sock Shop deployed in `cascade-targets`
- Chaos Mesh installed for real chaos tests
- explicit `-ConfirmLocalKind` on live demo scripts

Setup and verification:

```powershell
.\scripts\deploy-targets.ps1
.\scripts\install-chaos-mesh.ps1 -ConfirmLocalKind
.\scripts\verify-chaos-mesh.ps1
.\scripts\ensure-redpanda-topics.ps1
```

Run bounded, policy-gated live demos:

```powershell
.\scripts\demo-real-chaos.ps1 -ConfirmLocalKind
.\scripts\demo-real-remediation.ps1 -ConfirmLocalKind
```

The scripts temporarily enable live-demo flags on the relevant executor and require approval records plus dry-run-first validation. The real chaos demo creates a bounded plan, runs `/runs` with `dry_run=true`, records an approved local-demo decision through `approval-service`, then submits real execution with both the returned `approval_id` and `approved=true`. The real remediation demo creates a `restart_deployment` plan with rollback steps and post-checks, runs `/executions/dry-run`, records approval, then submits `/executions` with the returned `approval_id` and `dry_run=false`. They are scoped to `cascade-targets` and safe Sock Shop services such as `catalogue`; they intentionally block `cascade-system`, databases, brokers, session stores, wildcard selectors, namespace deletion, and deployment deletion.

Disable live mode and clean up:

```powershell
kubectl -n cascade-targets delete podchaos,networkchaos,stresschaos -l cascade.io/phase=phase7 --ignore-not-found=true
powershell -ExecutionPolicy Bypass -File .\scripts\disable-ui-live-demo.ps1
```

This is local demo mode only. It is opt-in, bounded, policy-gated, approval-required, and dry-run-first; it is not production safety guidance.

## Useful Scripts

Deployment:

```powershell
.\scripts\deploy.ps1
```

Acceptance:

```powershell
.\scripts\accept.ps1
.\scripts\accept-all.ps1
```

Debugging:

```powershell
.\scripts\debug.ps1
.\scripts\debug-all.ps1
```

Demo:

```powershell
.\scripts\demo.ps1 -NoBrowser
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
targets/sock-shop/            Canonical demo target workload
targets/online-boutique-src/  Inactive legacy/vendor snapshot
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
- `docs/operations/target-workload-integration.md`
- `docs/operations/target-onboarding-checklist.md`
- `targets/template/README.md`
- `scripts/validate-target.ps1`
- `docs/chaos.md`
- `docs/remediation.md`
- `docs/operations/ci-cd.md`
- `docs/operations/runbook.md`
- `docs/operations/backups.md`
- `docs/operations/secret-hygiene.md`
