# Phase 7 - Chaos Engineering Automation

Phase 7 lets Cascade safely plan, execute, observe, and score controlled Chaos Mesh experiments against the Online Boutique target namespace.

Phase 7 executes controlled chaos only. It does not execute remediation, patch application deployments, scale workloads, run autonomous agent-triggered chaos, or provide a UI.

## Architecture

```text
topology / anomalies / incidents / knowledge
-> chaos-planner-service
-> chaos_experiment_plans
-> chaos-executor-service
-> Chaos Mesh CRDs in cascade-targets
-> chaos_observations / resilience_scores
-> chaos.experiments
-> optional Phase 6 investigation
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
- Online Boutique services only
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
- optionally starts a Phase 6 deterministic investigation
- stores `chaos_observations`
- computes and stores `resilience_scores`

The baseline score starts high for bounded, cleaned-up experiments and penalizes anomaly count, incident count, broader blast radius, and cleanup failure. Grades:

- A: `>= 0.90`
- B: `>= 0.75`
- C: `>= 0.60`
- D: `>= 0.40`
- F: `< 0.40`

## ClickHouse Schema

Phase 7 adds:

- `chaos_experiment_plans`
- `chaos_experiment_runs`
- `chaos_observations`
- `resilience_scores`
- `chaos_safety_violations`

## Redpanda Topic

Phase 7 adds `chaos.experiments`.

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
.\scripts\deploy-phase-7.ps1
```

Acceptance:

```powershell
.\scripts\accept-phase-7.ps1
```

Non-disruptive acceptance:

```powershell
.\scripts\accept-phase-7.ps1 -DryRunOnly
```

Demo:

```powershell
.\scripts\demo-phase-7.ps1 -DryRunOnly
.\scripts\demo-phase-7.ps1 -TargetService recommendationservice -ObservationWindowSeconds 60
```

Debug:

```powershell
.\scripts\debug-phase-7.ps1
```

Reset:

```powershell
.\scripts\reset-phase-7.ps1
```

Use `-ClearPhase7Tables` only when intentionally clearing local Phase 7 rows.

## Known Limitations

- Phase 7 executes controlled chaos only.
- No remediation execution.
- No autonomous agent-triggered chaos by default.
- No UI.
- Network and stress experiments are local-limited and optional.
- Resilience scores are baseline heuristics.
- Dry-run mode is available for safe validation.
