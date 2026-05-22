# Chaos engineering - Chaos Engineering Automation

Chaos engineering lets Cascade safely plan, execute, observe, and score controlled Chaos Mesh experiments against the Sock Shop target namespace.

Chaos engineering is dry-run by default. Real Chaos Mesh execution is available only through the opt-in local demo script or local live-demo Command Center mode and requires live-demo flags, local kind context validation, approval, and a prior successful dry-run.

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
- `POST /campaigns`
- `GET /campaigns`
- `GET /campaigns/{campaign_id}`
- `POST /campaigns/{campaign_id}/start`
- `POST /campaigns/{campaign_id}/pause`
- `POST /campaigns/{campaign_id}/resume`
- `POST /campaigns/{campaign_id}/stop`
- `GET /campaign-runs`
- `GET /campaigns/{campaign_id}/runs`
- `GET /campaign-runs/{run_id}/report`

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

## Chaos Campaigns

Chaos campaigns are repeatable sets of bounded templates. A campaign defines a name, target namespace, allowed services, experiment templates, schedule metadata, max experiments per run, blast-radius limit, cooldown, dry-run mode, and local-demo execution intent.

Campaign starts are safe by default:

- new campaigns default to dry-run
- Command Center exposes only dry-run campaign creation and starts unless live-demo proxy gates are enabled
- each template creates a normal chaos plan and reuses the existing safety validator
- each experiment is executed by `chaos-executor-service`, so real execution still requires approval, dry-run-first history, local kind context, live-demo flags, and allowlists
- blocked templates are recorded with reasons instead of bypassing policy
- cleanup remains delegated to the existing executor, which deletes Cascade-managed Chaos Mesh resources during failure handling

The first campaign implementation is manually/API triggered. Schedule metadata and `next_run_at` are stored so campaigns are repeatable, but there is no always-on background scheduler yet.

Campaign reports include experiments run, services targeted, failures observed, RCA summaries from retrieval/RCA, recommendations, and skipped or blocked experiments with reasons.

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
- `chaos_campaigns`
- `chaos_campaign_runs`
- `chaos_campaign_steps`

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

Chaos acceptance is non-disruptive by default and skips live failure injection unless explicitly requested. The older explicit dry-run form is still accepted:

```powershell
.\scripts\accept-chaos.ps1 -DryRunOnly
```

Only for authorized local/dev/staging clusters, opt in to the bounded live validation path:

```powershell
.\scripts\accept-chaos.ps1 -IncludeLiveChaos
```

Demo:

```powershell
.\scripts\demo-chaos.ps1 -DryRunOnly
.\scripts\demo-chaos.ps1 -TargetService catalogue -ObservationWindowSeconds 60
.\scripts\demo-chaos-campaign.ps1
```

Opt-in local live demo:

```powershell
.\scripts\install-chaos-mesh.ps1 -ConfirmLocalKind
.\scripts\verify-chaos-mesh.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\demo-real-chaos.ps1 -ConfirmLocalKind
```

The live demo performs a bounded one-pod `PodChaos` against an allowlisted Sock Shop service, `catalogue` by default, for 10-30 seconds. It temporarily enables `ENABLE_DANGEROUS_ACTIONS=true`, `ENABLE_REAL_CHAOS=true`, and `CASCADE_LIVE_DEMO_MODE=true` on the chaos executor, creates the plan, runs executor dry-run validation first, records an approved local-demo decision through the existing approval service, then executes the real run with both the returned `approval_id` and `approved=true`. The script cleans up Cascade-managed Chaos Mesh resources and disables the live flags in a `finally` block. It does not target `cascade-system`, databases, brokers, queues, auth stores, session stores, or wildcard selectors.

## Command Center UI Modes

Dry-run UI mode is the default. Testers can create bounded dry-run `pod_kill` plans and run executor dry-runs without mutating the cluster.

Local live-demo UI mode is optional and local-kind only. The UI shows `LIVE DEMO MODE` only when backend policy reports `ENABLE_DANGEROUS_ACTIONS=true`, `ENABLE_REAL_CHAOS=true`, `CASCADE_LIVE_DEMO_MODE=true`, and the allowed namespace is `cascade-targets`; the Command Center proxy must also be explicitly enabled. Use the UI toggle script:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\enable-ui-live-demo.ps1 -ConfirmLocalKind
```

In that mode the UI exposes only bounded `pod_kill` against policy-allowlisted safe services, requires a confirmation checkbox, and follows the same plan -> dry-run -> approval -> approval-status -> real run flow as the script. The backend still rejects protected services, missing approval, missing dry-run, disallowed namespaces, and wildcard selectors. Disable the proxy flag after the local demo:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\disable-ui-live-demo.ps1
```

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

- Real execution is local demo mode only and remains disabled by default.
- No remediation execution.
- No autonomous agent-triggered chaos by default.
- Campaign schedule metadata is persisted, but this MVP does not include a continuously running background scheduler.
- Browser-based real execution is limited to local live-demo mode and the bounded `pod_kill` flow.
- Network and stress experiments are local-limited and optional.
- Resilience scores are baseline heuristics.
- Dry-run mode is available for safe validation.
