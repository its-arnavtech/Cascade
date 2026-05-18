# Chaos engineering - Chaos Engineering Automation

Chaos engineering lets Cascade safely plan, execute, observe, and score controlled Chaos Mesh experiments against the Sock Shop target namespace.

Chaos engineering is dry-run by default. Real Chaos Mesh execution is available only through the opt-in local demo script and requires live-demo flags, local kind context validation, approval, and a prior successful dry-run.

## Architecture

```text
topology / anomalies / incidents / knowledge
-> chaos-planner-service
-> chaos_experiment_plans
-> chaos-executor-service
-> Chaos Mesh CRDs in cascade-targets
-> chaos_observations / resilience_scores
-> chaos.experiments
-> optional Agent investigations investigation
```

Existing Cascade services remain the source of truth for telemetry, anomalies, incidents, topology, knowledge, and investigations.

## Services

### chaos-planner-service

Generates bounded experiment plans and stores them in ClickHouse.

Endpoints:

- `GET /health`
- `GET /ready`
- `POST /plans`
- `GET /plans`
- `GET /plans/{plan_id}`
- `POST /plans/from-anomaly`
- `POST /plans/{plan_id}/validate`

### chaos-executor-service

Re-validates safety, executes approved Chaos Mesh plans, cleans up resources, observes impact, computes resilience scores, and emits lifecycle events.

Endpoints:

- `GET /health`
- `GET /ready`
- `GET /safety/policy`
- `POST /runs`
- `GET /runs`
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/cleanup`
- `POST /runs/{run_id}/observe`
- `GET /scores/recent`

## Safety Model

Default allowlist:

- namespace: `cascade-targets`
- Sock Shop safe chaos services only
- experiment kinds: `pod_kill`, `network_delay`, `stress_cpu`

Default denylist:

- `kube-system`
- `kube-public`
- `kube-node-lease`
- `local-path-storage`
- `monitoring`
- `cascade-system`
- `default`

Safety checks reject:

- non-allowlisted namespaces
- denied namespaces
- non-allowlisted services
- broad or empty selectors
- unsupported experiment kinds
- durations above the configured maximum
- real execution without `approved=true`
- real execution without live-demo flags, local kind context, non-expired approval, and prior successful dry-run
- manifests missing Cascade cleanup labels

The executor ServiceAccount can get/list/watch pods and services in `cascade-targets` and create/get/list/watch/delete Chaos Mesh resources in `cascade-targets`. It cannot mutate deployments, services, configmaps, secrets, or system namespaces.

## Supported Templates

`pod_kill`:

- Chaos Mesh `PodChaos`
- action: `pod-kill`
- mode: `one`
- selector: one allowlisted service in `cascade-targets`

`network_delay`:

- Chaos Mesh `NetworkChaos`
- action: `delay`
- bounded latency, jitter, and duration

`stress_cpu`:

- Chaos Mesh `StressChaos`
- low CPU load
- short bounded duration

Acceptance defaults to `pod_kill`.

## Observation And Scoring

After a real run, the executor:

- queries recent telemetry for the target service
- queries recent anomalies
- queries recent incidents
- optionally starts a Agent investigations deterministic investigation
- stores `chaos_observations`
- computes and stores `resilience_scores`

The baseline score starts high for bounded, cleaned-up experiments and penalizes anomaly count, incident count, broader blast radius, and cleanup failure. Grades:

- A: `>= 0.90`
- B: `>= 0.75`
- C: `>= 0.60`
- D: `>= 0.40`
- F: `< 0.40`

## ClickHouse Schema

Chaos engineering adds:

- `chaos_experiment_plans`
- `chaos_experiment_runs`
- `chaos_observations`
- `resilience_scores`
- `chaos_safety_violations`

`chaos_experiment_runs` stores lifecycle state transitions. The run APIs return the latest canonical row per `run_id` by default, so `/runs` shows one current state per run and `/runs/{run_id}` resolves completed or failed terminal state after cleanup.

## Redpanda Topic

Chaos engineering adds `chaos.experiments`.

Lifecycle events include:

- `chaos.plan.created`
- `chaos.plan.rejected`
- `chaos.run.started`
- `chaos.run.completed`
- `chaos.run.failed`
- `chaos.run.cleaned_up`
- `chaos.observation.completed`
- `chaos.resilience.scored`

Events are compact. Raw manifests and reports stay in ClickHouse/API responses.

## Workflows

Deploy:

```powershell
.\scripts\deploy-chaos.ps1
```

Acceptance:

```powershell
.\scripts\accept-chaos.ps1
```

Non-disruptive acceptance:

```powershell
.\scripts\accept-chaos.ps1 -DryRunOnly
```

Demo:

```powershell
.\scripts\demo-chaos.ps1 -DryRunOnly
.\scripts\demo-chaos.ps1 -TargetService catalogue -ObservationWindowSeconds 60
```

Opt-in local live demo:

```powershell
.\scripts\install-chaos-mesh.ps1 -ConfirmLocalKind
.\scripts\verify-chaos-mesh.ps1
.\scripts\demo-real-chaos.ps1 -ConfirmLocalKind
```

The live demo performs a bounded one-pod `PodChaos` against an allowlisted Sock Shop service, `catalogue` by default, for 10-30 seconds. It temporarily enables `ENABLE_DANGEROUS_ACTIONS=true`, `ENABLE_REAL_CHAOS=true`, and `CASCADE_LIVE_DEMO_MODE=true` on the chaos executor only, creates the plan, runs executor dry-run validation first, records an approved local-demo decision through the existing approval service, then executes the real run with both the returned `approval_id` and `approved=true`. The script cleans up Cascade-managed Chaos Mesh resources and disables the live flags in a `finally` block. It does not target `cascade-system`, databases, brokers, session stores, or wildcard selectors.

Debug:

```powershell
.\scripts\debug-chaos.ps1
```

Reset:

```powershell
.\scripts\reset-chaos.ps1
```

Use `-ClearChaosTables` only when intentionally clearing local Chaos engineering rows.

## Known Limitations

- Real execution is scripts-only local demo mode and remains disabled by default.
- No remediation execution.
- No autonomous agent-triggered chaos by default.
- No browser-based real execution path.
- Network and stress experiments are local-limited and optional.
- Resilience scores are baseline heuristics.
- Dry-run mode is available for safe validation.
