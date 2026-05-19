# Final Cascade Demo Guide

## Prerequisites

- Docker Desktop or Docker Engine
- kind cluster named `cascade`
- kubectl context `kind-cascade`
- PowerShell
- Node.js/npm for the Command Center build
- Python test dependencies installed locally

## Deploy And Validate

```powershell
.\scripts\deploy.ps1
.\scripts\accept.ps1
.\scripts\accept-all.ps1
```

## Open The Demo Surfaces

Command Center:

```powershell
kubectl port-forward -n cascade-system svc/command-center 18300:8030
```

Open `http://localhost:18300`.

Useful local forwards:

```powershell
kubectl port-forward -n cascade-system svc/clickhouse 18123:8123
kubectl port-forward -n cascade-system svc/qdrant 16333:6333
kubectl port-forward -n cascade-system svc/retrieval-service 18012:8012
```

If Prometheus or Grafana are installed in your local Observability foundation environment, forward them using their existing services in the cluster.

## Recommended Flow

1. Show the Sock Shop target workload running in `cascade-targets`.
2. Show Prometheus/Grafana metrics if those Observability foundation observability services are running.
3. Open Command Center overview and telemetry pages.
4. Show anomaly data and retrieval counts.
5. Search knowledge/runbook content.
6. Trigger a deterministic investigation.
7. Create a chaos dry-run plan and show that real chaos is disabled by default.
8. Create a remediation plan, approve it, run dry-run validation, and show that real execution remains disabled by default.
9. Show safety policies, rate-limit configuration, and the final support bundle script.

The Command Center UI has two modes:

- Dry-run UI mode: default, safe for testers, and no real cluster mutation.
- Local live-demo UI mode: optional, local kind only, and requires live-demo flags plus the Command Center proxy gate. The UI shows `LIVE DEMO MODE`, exposes only bounded `pod_kill` chaos and `restart_deployment` remediation for allowlisted `cascade-targets` services, and still relies on backend approval, dry-run-first, rollback, post-check, protected-service, and namespace checks.

Optional local live demo, only after the dry-run flow passes:

```powershell
.\scripts\install-chaos-mesh.ps1 -ConfirmLocalKind
powershell -ExecutionPolicy Bypass -File .\scripts\demo-real-chaos.ps1 -ConfirmLocalKind
powershell -ExecutionPolicy Bypass -File .\scripts\demo-real-remediation.ps1 -ConfirmLocalKind
```

To test the browser live path after enabling executor flags, also enable the Command Center proxy gate:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\enable-ui-live-demo.ps1 -ConfirmLocalKind
```

Disable it after the local demo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\disable-ui-live-demo.ps1
```

These commands are opt-in, bounded, policy-gated, approval-required, and dry-run-first. They are local demo mode only and do not imply production safety.

## Troubleshooting

- Missing Command Center endpoints: rerun `.\scripts\deploy.ps1`.
- Redpanda topic mismatch: run `.\scripts\ensure-redpanda-topics.ps1`.
- Too much demo data: use latest-state queries or reset component state with the relevant `reset-*.ps1` helper.
- Unknown UI API error: run `.\scripts\debug.ps1` or `.\scripts\debug-all.ps1`.

## Known Limits

Cascade is a production-inspired local reliability platform, not a production deployment. Local kind storage, in-memory rate limiting, and dry-run safety defaults are intentional boundaries for demo and portfolio use.
