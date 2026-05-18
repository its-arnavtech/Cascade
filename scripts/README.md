# Cascade Scripts

Use these scripts from the repository root unless a script says otherwise.

| Script | Purpose |
|---|---|
| `deploy.ps1` | Deploy all Cascade services to local kind |
| `accept.ps1` | Run end-to-end acceptance validation |
| `demo.ps1` | Run the full interactive demo flow |
| `debug.ps1` | Dump logs and diagnostics for all services |
| `accept-all.ps1` | Full suite validation across all components |
| `debug-all.ps1` | Full diagnostic sweep |
| `ci-local.ps1` | Run CI checks locally |
| `audit-secrets.ps1` | Scan tracked files for leaked secrets |
| `deploy-targets.ps1` | Deploy the canonical Sock Shop target workload |
| `validate-target.ps1` | Read-only readiness validation for a target workload namespace |
| `configure-target.ps1` | Register a target config with running Cascade deployments |
| `ensure-redpanda-topics.ps1` | Ensure required Kafka-compatible Redpanda topics exist |
| `verify-chaos-mesh.ps1` | Verify local Chaos Mesh CRDs/controller and Cascade namespace protections |
| `install-chaos-mesh.ps1` | Install or upgrade Chaos Mesh for explicitly confirmed local kind demos |
| `demo-real-chaos.ps1` | Run opt-in bounded real chaos in local demo mode |
| `demo-real-remediation.ps1` | Run opt-in bounded real remediation in local demo mode |

## Quick Start

```powershell
.\scripts\deploy.ps1
.\scripts\deploy-targets.ps1
.\scripts\accept.ps1
.\scripts\demo.ps1 -NoBrowser
```

Open the Command Center after deployment:

```powershell
kubectl port-forward -n cascade-system svc/command-center 18300:8030
```

Then browse to `http://localhost:18300`.

## Component Helpers

The main scripts are the demo-facing entrypoints. Component-scoped helpers are kept for targeted development and recovery without reintroducing numbered scaffolding:

| Area | Deploy | Accept | Demo | Debug | Reset |
|---|---|---|---|---|---|
| Telemetry pipeline | `deploy-telemetry.ps1` | `accept-telemetry.ps1` | `demo-telemetry.ps1` | - | - |
| Storage and memory | `deploy-storage-memory.ps1` | `accept-storage-memory.ps1` | `demo-storage-memory.ps1` | `debug-storage-memory.ps1` | `reset-storage-memory.ps1` |
| Anomaly detection | `deploy-anomaly-detection.ps1` | `accept-anomaly-detection.ps1` | `demo-anomaly-detection.ps1` | `debug-anomaly-detection.ps1` | `reset-anomaly-detection.ps1` |
| Knowledge and RAG | `deploy-knowledge-rag.ps1` | `accept-knowledge-rag.ps1` | `demo-knowledge-rag.ps1` | `debug-knowledge-rag.ps1` | `reset-knowledge-rag.ps1` |
| Agent investigations | `deploy-agents.ps1` | `accept-agents.ps1` | `demo-agents.ps1` | `debug-agents.ps1` | `reset-agents.ps1` |
| Chaos engineering | `deploy-chaos.ps1` | `accept-chaos.ps1` | `demo-chaos.ps1` | `debug-chaos.ps1` | `reset-chaos.ps1` |
| Remediation | `deploy-remediation.ps1` | `accept-remediation.ps1` | `demo-remediation.ps1` | `debug-remediation.ps1` | `reset-remediation.ps1` |
| Command Center UI | `deploy.ps1` | `accept.ps1` | `demo.ps1` | `debug.ps1` | `reset-command-center.ps1` |

## Bring Your Own Target

Default safe path:

```powershell
kubectl create namespace cascade-targets --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace cascade-targets cascade.io/monitored=true --overwrite
kubectl apply -n cascade-targets -f path\to\your-app.yaml

.\scripts\validate-target.ps1 -Namespace cascade-targets -ExpectedServices frontend,api -ShowLabels
```

Target config path:

```powershell
Copy-Item -Recurse targets\template targets\my-app
notepad targets\my-app\target.yaml

.\scripts\validate-target.ps1 -Namespace cascade-targets -TargetConfig targets\my-app\target.yaml -Strict
.\scripts\configure-target.ps1 -TargetConfig targets\my-app\target.yaml
.\scripts\ensure-redpanda-topics.ps1
.\scripts\accept-telemetry.ps1
```

`validate-target.ps1` is read-only. `configure-target.ps1` changes Cascade deployment environment and config mounts; use `-DryRun` to preview first.

## Validation And Safety

Run the full local acceptance suite:

```powershell
.\scripts\accept-all.ps1
```

Run local CI checks:

```powershell
.\scripts\ci-local.ps1 -SkipDockerBuild
```

Run secret hygiene before publishing:

```powershell
.\scripts\audit-secrets.ps1
```

Useful safe flags:

- `-DryRunOnly` keeps chaos validation non-disruptive.
- `validate-target.ps1 -Strict` exits nonzero when readiness checks fail.
- `configure-target.ps1 -DryRun` previews target registration without changing deployments.
- `-NoBrowser` prevents demo scripts from opening a browser.
- `-ConfirmRestore` is required before restore scripts mutate local data stores.
- `-SkipDockerBuild` skips Docker image smoke builds in local CI.

## Optional Live Local-Demo Path

Dry-run acceptance is the default. The following scripts are for explicitly confirmed local-kind resilience testing only:

```powershell
.\scripts\install-chaos-mesh.ps1 -ConfirmLocalKind
.\scripts\verify-chaos-mesh.ps1
.\scripts\demo-real-chaos.ps1 -ConfirmLocalKind
.\scripts\demo-real-remediation.ps1 -ConfirmLocalKind
```

Live controlled failure injection and live remediation remain opt-in, policy-gated, and unsuitable for production.

Backups and restores:

- `backup-clickhouse.ps1`, `list-clickhouse-backups.ps1`, `restore-clickhouse.ps1`
- `backup-qdrant.ps1`, `list-qdrant-backups.ps1`, `restore-qdrant.ps1`

Generated logs, support bundles, backups, local `.env` files, kubeconfigs, and database volumes are ignored by `.gitignore` and should not be committed.
