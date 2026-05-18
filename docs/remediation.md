# Remediation - Remediation + Human Approval

Remediation adds the remediation control plane for Cascade. It recommends safe next steps from real Cascade evidence, records human approval decisions, validates actions with dry-run checks, and blocks real execution by default.

## Architecture

```text
incidents/anomalies/investigations/chaos scores/knowledge
-> remediation-recommender-service
-> ClickHouse remediation_plans
-> approval-service
-> ClickHouse remediation_approvals
-> remediation-executor-service
-> dry-run validation / optional gated execution
-> ClickHouse remediation_executions
-> Redpanda remediation.actions
```

## Services

- `remediation-recommender-service`: deterministic plan generation, evidence gathering, rollback/runbook steps, safety validation, plan persistence, and `remediation.plan.created` events.
- `approval-service`: explicit human approve/reject records with approver metadata, reasons, expiration, and approval lifecycle events. It never executes actions.
- `remediation-executor-service`: policy re-validation, Kubernetes server-side dry-run where applicable, execution records, safety violations, and optional allowlisted execution when deliberately enabled.

## Safety Model

Safety is deny-by-default:

- allowed namespace defaults to `cascade-targets`.
- denied namespaces include `kube-system`, `kube-public`, `kube-node-lease`, `local-path-storage`, `monitoring`, `cascade-system`, and `default`.
- services must be allowlisted Sock Shop/Cascade target services.
- evidence refs are required for recommendations.
- rollback steps are required for executable actions.
- broad selectors are rejected.
- secrets, configmaps, RBAC, service accounts, and namespaces cannot be mutated.
- human approval is required for real execution.
- `EXECUTION_ENABLED=false` by default blocks real execution.
- live-demo execution also requires `ENABLE_DANGEROUS_ACTIONS=true`, `ENABLE_REAL_REMEDIATION=true`, `CASCADE_LIVE_DEMO_MODE=true`, the allowlisted local context, and a prior successful dry-run.
- no arbitrary shell commands or LLM-generated executable commands are accepted.

## Supported Action Types

- `investigate_only`: text-only recommendation and next investigation steps. This is the default acceptance/demo action.
- `restart_deployment`: command text and server-side dry-run deployment patch. Real execution is optional and disabled by default.
- `scale_deployment_noop`: validates a same-replica scale patch. Real execution is a no-op and disabled by default.
- `rollback_deployment`: text recommendation plus dry-run style validation where possible. No real rollback by default.
- `cleanup_cascade_chaos_resource`: optional cleanup only for Cascade-managed Chaos Mesh resources with `cascade.io/phase=phase7` and `cascade.io/managed-by=chaos-executor-service`.

## Approval Workflow

1. Create a plan with `POST /plans`.
2. Review evidence refs, remediation steps, rollback steps, confidence, and safety findings.
3. Record a decision with `POST /approvals`.
4. Query latest approval with `GET /plans/{plan_id}/approval-status`.
5. Run dry-run validation with `POST /executions/dry-run`.

Rejections require a reason. Approvals include an expiration window.

## Dry-run And Execution

Default Remediation workflows are dry-run only. `POST /executions/dry-run` stores a `remediation_executions` row with `dry_run=1` and `executed=0`.

`POST /executions` with `dry_run=false` requires all of the following:

- valid non-expired approval.
- safety validation passes.
- action type is executable.
- namespace and service are allowlisted.
- rollback steps exist.
- post-checks exist.
- `EXECUTION_ENABLED=true`.
- Kubernetes RBAC permits the specific action.

The default deployment sets `EXECUTION_ENABLED=false`, so acceptance verifies that real execution is rejected.

## Opt-in Local Live Demo

Real remediation is scripts-only for public local demos:

```powershell
.\scripts\demo-real-remediation.ps1 -ConfirmLocalKind
```

The script verifies `kind-cascade`, `cascade-targets`, a safe Sock Shop service, rollback steps, post-checks, and dry-run validation before executing. The default action is `restart_deployment` for `catalogue`. It creates a plan, runs `POST /executions/dry-run`, records a non-expired approval through `approval-service`, verifies approval status, then calls `POST /executions` with the returned `approval_id` and `dry_run=false`. Rollback and post-check requirements are satisfied by the persisted plan fields. It temporarily enables `EXECUTION_ENABLED=true`, `ENABLE_DANGEROUS_ACTIONS=true`, `ENABLE_REAL_REMEDIATION=true`, and `CASCADE_LIVE_DEMO_MODE=true` on the remediation executor, then disables them in a `finally` block.

Intentionally blocked actions include namespace deletion, deployment deletion, database or broker mutation, `cascade-system` mutation, protected services, wildcard selectors, and any action without rollback/post-checks.

## ClickHouse Schema

Remediation adds:

- `remediation_plans`
- `remediation_approvals`
- `remediation_executions`
- `remediation_safety_violations`
- `remediation_policy_audit`

Schema initialization is idempotent and does not destroy existing data.

## Redpanda Topic

Topic: `remediation.actions`

Events are compact and omit secrets and large manifests. Event types include plan creation/rejection, approval/rejection, dry-run lifecycle, and execution lifecycle.

## RBAC Boundaries

`remediation-executor-service` uses a dedicated service account. It receives scoped permissions in `cascade-targets` for:

- read pods/services.
- get/list/watch/patch deployments and deployment scale.
- get/list/watch/delete Chaos Mesh resources for optional managed cleanup.

It has no cluster-admin role and no permissions for secrets, configmaps, RBAC, service accounts, namespaces, or system namespaces.

## API Reference

### Remediation Recommender

- `GET /health`
- `GET /ready`
- `POST /plans`
- `GET /plans`
- `GET /plans/{plan_id}`
- `POST /plans/from-latest-investigation`
- `POST /plans/from-latest-anomaly`
- `POST /plans/{plan_id}/validate`

### Approval Service

- `GET /health`
- `GET /ready`
- `POST /approvals`
- `GET /approvals`
- `GET /approvals/{approval_id}`
- `GET /plans/{plan_id}/approval-status`

### Remediation Executor

- `GET /health`
- `GET /ready`
- `GET /safety/policy`
- `POST /executions/dry-run`
- `POST /executions`
- `GET /executions`
- `GET /executions/{execution_id}`

## Deploy Workflow

```powershell
.\scripts\deploy-remediation.ps1
```

This builds Remediation images, applies schema/topic jobs, deploys services/RBAC, and waits for rollouts.

## Acceptance Workflow

```powershell
.\scripts\accept-remediation.ps1
```

Acceptance checks Chaos engineering readiness, Remediation schema/topic, service readiness, plan creation, safety rejection, approvals, dry-run validation, real execution blocking, agent gateway tools, and list APIs.

## Demo Workflow

```powershell
.\scripts\demo-remediation.ps1
```

The demo shows plan generation, evidence, rollback steps, safety policy, unsafe rejection, approval, dry-run validation, and real execution disabled by default.

## Troubleshooting

Run:

```powershell
.\scripts\debug-remediation.ps1
```

It collects pod/service status, events, Redpanda topics, ClickHouse counts, recent plans/approvals/executions/violations, logs, health/ready output, safety policy, and recent API responses.

## Known Limitations

- real execution is disabled by default.
- live execution is local demo mode only and scripts-only.
- no production authentication/RBAC yet.
- recommendations are deterministic/template-based.
- no arbitrary commands are accepted.
- no LLM-generated execution is supported.
- production hardening, rate limits, backups, and credential hardening are Hardening.
