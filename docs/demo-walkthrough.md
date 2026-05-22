# Cascade Demo Walkthrough

This walkthrough is the safe, presenter-friendly path for showing Cascade as a Kubernetes reliability platform. It uses Sock Shop by default, keeps real chaos and real remediation disabled, and labels weak evidence instead of pretending certainty.

## What Cascade Shows

Cascade observes a target workload, collects telemetry, builds feature windows, detects anomalies, reconstructs likely root cause evidence, predicts blast radius from topology, recommends policy-gated remediation, and can run Autopilot in dry-run mode.

## Start Cascade

```powershell
.\scripts\deploy.ps1
.\scripts\deploy-targets.ps1
.\scripts\ensure-redpanda-topics.ps1
```

Open Command Center:

```powershell
kubectl port-forward -n cascade-system svc/command-center 18300:8030
```

Then browse to `http://localhost:18300`.

## One-Command Safe Demo

Run the full dry-run-first demo path:

```powershell
.\scripts\demo-command-center.ps1 -Stage All
```

Or run it in smaller beats:

```powershell
.\scripts\demo-command-center.ps1 -Stage Validate
.\scripts\demo-command-center.ps1 -Stage Telemetry
.\scripts\demo-command-center.ps1 -Stage Chaos
.\scripts\demo-command-center.ps1 -Stage Remediation
.\scripts\demo-command-center.ps1 -Stage Autopilot
```

The wrapper does not enable live chaos or live remediation. It prints the expected dashboard result after each stage.

## What To Point Out

- **Overview**: system health, active anomalies, recent RCA, Autopilot runs, remediation status, verification/rollback, chaos experiments, topology summary, and demo commands.
- **Topology**: active target workload, dependency graph, and blast-radius analysis.
- **Causality**: RCA evidence bundle with confidence, affected services, related chaos experiment, and limitations.
- **Chaos**: policy-gated dry-run plans and runs. Live local chaos is hidden unless explicitly enabled.
- **Remediation**: evidence-backed plan, approval record, dry-run validation, rollback and verification status.
- **Autopilot**: state strip for investigated, planned, policy checked, dry-run, executed or blocked, and verified.

## Reset

```powershell
.\scripts\demo-command-center.ps1 -Stage Reset
```

This disables UI live-demo mode and resets Command Center state. Component-level reset scripts remain available in `scripts/README.md`.

## Optional Local Live Demo

Only use live chaos/remediation on a local kind cluster you control:

```powershell
.\scripts\enable-ui-live-demo.ps1 -ConfirmLocalKind
.\scripts\demo-real-chaos.ps1 -ConfirmLocalKind
.\scripts\demo-real-remediation.ps1 -ConfirmLocalKind
.\scripts\disable-ui-live-demo.ps1
```

Do not use live chaos or live remediation against production.

## Known Limitations

- Prometheus metrics are opportunistic; if unavailable, Cascade uses Kubernetes fallback data and labels missing metrics.
- RCA confidence depends on telemetry history and topology quality.
- Autopilot dry-run validates the loop but does not perform unrestricted self-healing.
- Screenshots are not checked in yet. If release screenshots are added later, place them under `docs/demo/` and reference them from this walkthrough.
