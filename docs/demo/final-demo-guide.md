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
.\scripts\deploy-phase-9.ps1
.\scripts\accept-phase-9.ps1
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

If Prometheus, Grafana, or Online Boutique are installed in your local Phase 1 environment, forward them using their existing services in the cluster.

## Recommended Flow

1. Show the Online Boutique target workload running in `cascade-targets`.
2. Show Prometheus/Grafana metrics if those Phase 1 observability services are running.
3. Open Command Center overview and telemetry pages.
4. Show anomaly data and retrieval counts.
5. Search knowledge/runbook content.
6. Trigger a deterministic investigation.
7. Create a chaos dry-run plan and show that real chaos is blocked by default.
8. Create a remediation plan, approve it, run dry-run validation, and show that real execution remains blocked.
9. Show safety policies, rate-limit configuration, and the final support bundle script.

## Troubleshooting

- Missing Command Center endpoints: rerun `.\scripts\deploy-phase-9.ps1`.
- Redpanda topic mismatch: run `.\scripts\ensure-redpanda-topics.ps1`.
- Too much demo data: use latest-state queries or reset phase state with the relevant `reset-phase-*.ps1` script.
- Unknown UI API error: run `.\scripts\debug-phase-9.ps1` or `.\scripts\debug-all.ps1`.

## Known Limits

Cascade is a production-inspired local reliability platform, not a production deployment. Local kind storage, in-memory rate limiting, and dry-run safety defaults are intentional boundaries for demo and portfolio use.
