# Command Center UI - Command Center

## Purpose

Command Center UI adds an operator-facing web UI for Cascade. Operators can inspect telemetry, anomalies, incidents, knowledge, deterministic investigations, chaos dry-runs, remediation plans, approvals, dry-run executions, and service health from one browser entrypoint.

## Architecture

```text
Browser
  -> command-center service :8030
  -> /api/*
  -> command-center-api service :8031
  -> retrieval / knowledge / agent / chaos / remediation services
```

The frontend is a React, TypeScript, Vite app served by nginx. The backend-for-frontend is a small FastAPI proxy with fixed upstream routes only.

## UI Pages

- `/` overview dashboard with counts, health, and recent activity.
- `/telemetry` recent telemetry events, filters, feature windows, and basic charts.
- `/anomalies` recent anomalies and safe investigation creation.
- `/incidents` incident list, detail/report viewer, investigation and plan entrypoints.
- `/knowledge` source-grounded search and deterministic context packs.
- `/investigations` deterministic investigation creation, runs, steps, tool calls, and reports.
- `/chaos` safety policy, plans, dry-run runs, resilience scores, and dry-run execution only.
- `/remediation` safety policy, plans, approvals/rejections, dry-run validation, and executions.
- `/system` service health checks and debug counts.
- `/about` architecture, safety boundaries, local commands, and Hardening notes.

## API Proxy / BFF

`services/command-center-api` exposes:

- `GET /health`
- `GET /ready`
- `/api/retrieval/*`
- `/api/knowledge/*`
- `/api/agent/*`
- `/api/tools/*`
- `/api/chaos/planner/*`
- `/api/chaos/executor/*`
- `/api/remediation/recommender/*`
- `/api/remediation/approval/*`
- `/api/remediation/executor/*`
- `/api/anomaly/*`
- `/api/features/*`

Only `GET` and `POST` are accepted. The client cannot supply arbitrary upstream URLs. Known real-execution routes are blocked by default unless the proxy is explicitly configured with `ENABLE_DANGEROUS_ACTIONS=true`.

## Safety Model

The UI exposes reads, searches, deterministic investigation creation, plan creation, approval/rejection records, chaos dry-run execution, and remediation dry-run validation. Real remediation execution is disabled by default. Real chaos execution controls are hidden or blocked by default.

## Local Development

```powershell
cd web\command-center
npm install
npm run dev
```

Run the API proxy on `localhost:8031` or use Kubernetes and port-forward the command center.

## Kubernetes Deployment

```powershell
.\scripts\deploy.ps1
kubectl port-forward -n cascade-system svc/command-center 18300:8030
```

Open `http://localhost:18300`.

## Acceptance

```powershell
.\scripts\accept.ps1
```

The script validates Remediation baseline resources, UI deployments/endpoints, static assets, API proxy health, safe action flows, and frontend build.

## Demo

```powershell
.\scripts\demo.ps1 -NoBrowser
```

Use `-SkipActionDemo` to avoid creating new investigation/remediation dry-run records.

## Troubleshooting

```powershell
.\scripts\debug.ps1
kubectl -n cascade-system logs deployment/command-center
kubectl -n cascade-system logs deployment/command-center-api
```

If `/api/*` fails in the browser, verify `command-center-api` is ready and that nginx can resolve `command-center-api.cascade-system.svc.cluster.local`.

## Known Limitations

- No production authentication yet.
- No final rate limiting yet.
- No production backup workflows yet.
- Real remediation execution is disabled by default.
- Real chaos execution is hidden or disabled by default.
- Browser automation tests are minimal.
- Hardening will harden production security, backups, rate limits, and final polish.
