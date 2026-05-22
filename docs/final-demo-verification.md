# Final Demo Verification

Verification date: 2026-05-22 12:10 America/Chicago

This report captures the final local end-to-end demo verification for Cascade on `kind-cascade`. The run stayed in the safe default path: dry-run chaos, dry-run remediation, dry-run Autopilot, no live failure injection, and no live remediation.

## Commands Run

```powershell
git status --short
git branch --show-current

.\scripts\deploy.ps1
.\scripts\deploy-storage-memory.ps1

python -m pytest tests -q
python -m ruff check services tests
python -m compileall services tests
python scripts\validate-k8s-manifests.py
powershell -ExecutionPolicy Bypass -File .\scripts\audit-secrets.ps1

cd web\command-center
npm run typecheck
npm run build
cd ..\..

powershell -ExecutionPolicy Bypass -File .\scripts\accept.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\accept-all.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\demo-final.ps1
```

PowerShell parser checks were also run against changed tracked `.ps1` files and `scripts/demo-final.ps1`.

## Results

- Backend tests: PASS, `219 passed`.
- Ruff: PASS.
- Python compile: PASS.
- Kubernetes manifest validation: PASS, `76 Kubernetes YAML files`.
- Secret audit: PASS, no high-confidence secrets found.
- Frontend typecheck: PASS.
- Frontend build: PASS.
- `accept.ps1`: PASS.
- `accept-all.ps1`: PASS.
- `demo-final.ps1`: PASS.

Acceptance logs:

- `run-output\accept-all-20260522-120629`
- `run-output\final-demo\20260522-115950`

## Services Verified

The final demo script verified rollouts and service endpoints for:

- `command-center-api`
- `command-center`
- `topology-service`
- `observation-service`
- `retrieval-service`
- `feature-extractor-service`
- `anomaly-detector-service`
- `telemetry-archiver`
- `stream-enricher`
- `knowledge-retrieval-service`
- `agent-tool-gateway`
- `agent-orchestrator-service`
- `chaos-planner-service`
- `chaos-executor-service`
- `remediation-recommender-service`
- `approval-service`
- `remediation-executor-service`
- `autopilot-service`
- `scheduler-service`
- `experiment-tracker-service`
- `clickhouse`
- `redpanda`
- `qdrant`

## Demo Flow Verified

The safe final demo path verified:

- local prerequisites and kind context
- Cascade platform services and endpoints
- Sock Shop target namespace and `catalogue` service
- target validation via `scripts/validate-target.ps1`
- Command Center frontend and API proxy
- live-demo safety state with live chaos/remediation disabled
- telemetry, anomaly, topology, and RCA/causality API reachability
- topology refresh and graph retrieval
- dry-run chaos campaign creation and run
- dry-run Autopilot run
- remediation plan, plan-bound approval, and dry-run execution
- remediation, chaos, Autopilot, audit, and scheduler history APIs
- Command Center routes for overview, topology, causality/RCA, chaos, Autopilot, remediation, scheduler, audit, system, and about

## Screenshots

Screenshots were captured under:

```text
run-output\final-demo\screenshots
```

Captured routes:

- `overview.png`
- `topology.png`
- `causality.png`
- `chaos.png`
- `autopilot.png`
- `remediation.png`
- `scheduler.png`
- `audit.png`
- `system.png`
- `about.png`

These files are generated run artifacts and are not intended to be committed unless the repository later adopts tracked screenshot fixtures.

## Wiring Fixes Made

- Added `scripts/demo-final.ps1` as the final safe end-to-end product verifier.
- Linked the final demo verifier from `README.md` and `scripts/README.md`.
- Fixed `scripts/deploy-storage-memory.ps1` to restart `telemetry-archiver`, `memory-indexer`, and `retrieval-service` after rebuilding/loading images. The missing restart left the local cluster on an older retrieval-service pod that did not expose the current audit routes.

## Known Warnings

- `accept-telemetry.ps1` reported `Prometheus raw query failed, using Kubernetes snapshot fallback`. This is expected on the current local kind setup when Prometheus RED metrics are incomplete.
- `accept-chaos.ps1` skipped real chaos by default. This is intentional; live chaos remains opt-in only for authorized local/dev/staging runs.
- `accept-durability.ps1` skipped restart survival because `accept-all.ps1` runs it with `-SkipRestart`.
- `demo-final.ps1` may warn that `rca_reports` are empty on a fresh cluster until RCA reports are generated and stored.
- `demo-final.ps1` may warn that verification/rollback records are absent when only dry-run workflows have executed. Live remediation is required to create full post-remediation verification and rollback execution records, and that remains explicitly opt-in.

## Limitations

- The final demo intentionally does not prove live chaos or live remediation because those workflows require explicit local-demo opt-in and are not safe defaults.
- The local Prometheus path can still fall back to Kubernetes snapshots when RED metrics are unavailable.
- Screenshots verify route rendering and obvious layout health, not pixel-perfect visual regression.
- This is a local MVP verification, not a production readiness certification.

## Reproduce

From the repository root on a local kind setup:

```powershell
.\scripts\deploy.ps1
.\scripts\deploy-storage-memory.ps1
.\scripts\accept-all.ps1
.\scripts\demo-final.ps1
kubectl port-forward -n cascade-system svc/command-center 18300:8030
```

Open:

```text
http://localhost:18300/overview
```
