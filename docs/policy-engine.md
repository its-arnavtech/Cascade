# Policy Engine And Autonomy Gates

Cascade evaluates proposed remediation and Autopilot-facing actions through a shared policy engine before any execution path can continue. The policy decision is explanatory; backend executors still enforce approval, dry-run-first validation, rollback, post-check, namespace, protected-service, and live-demo checks.

## Autonomy Levels

| Level | Name | Behavior |
| --- | --- | --- |
| 0 | read-only investigation only | Allows read-only investigation and evidence gathering. |
| 1 | recommend only | Allows recommendations, but no mutating action. |
| 2 | dry-run fixes only | Allows dry-run validation for supported fixes. |
| 3 | auto-apply low-risk fixes | Allows low-risk, low-blast-radius actions when all safety gates pass. |
| 4 | require approval for risky fixes | Allows risky actions only after approval and execution gates pass. |
| 5 | never allowed actions | Blocks destructive or stateful actions regardless of mode. |

## Decision Outcomes

- `allowed`: policy permits the action after configured gates.
- `blocked`: policy rejects the action.
- `dry_run_only`: policy permits validation but not real mutation.
- `requires_approval`: policy allows the action only after human approval.
- `allowed_automatic`: policy permits automatic execution in a bounded low-risk or local-demo case.

Every decision includes reasons, risk level, blast radius, approval requirement, rollback availability, and an audit record. Remediation services write policy audit rows for plan validation and execution validation.

## Inputs Evaluated

The engine evaluates:

- action type, namespace, service/deployment, resource kind, and selectors.
- current mode: `read-only`, `dry-run`, `local-demo`, or `production-safe`.
- configured autonomy level.
- risk level and blast radius.
- rollback and post-check availability.
- action budget and recent action usage.
- namespace/service allowlists and denylists.
- protected services and never-allowed action classes.
- human approval state.

## Default Boundaries

Cascade defaults to `dry-run` behavior. Real mutating actions are blocked unless the executor and Command Center proxy are explicitly configured for local live-demo use or a future production-safe deployment supplies equivalent controls.

Never-allowed categories include namespace deletion, deployment deletion, StatefulSet deletion, secret/configmap patching, RBAC mutation, database changes, broker/queue changes, auth-store changes, session-store changes, wildcard selectors, `cascade-system`, and protected services.

## Remediation Integration

`remediation-recommender-service` attaches a `policy_decision` to generated plans and exposes read-only `POST /policy/evaluate`.

`remediation-executor-service` re-validates policy on dry-run and real execution and exposes read-only `POST /safety/evaluate`. Real execution still requires:

- `EXECUTION_ENABLED=true`.
- valid approval.
- prior successful dry-run.
- rollback steps.
- post-checks.
- safe namespace and service.
- live-demo flags for local live mode.

## Agent And Autopilot Integration

The agent tool gateway exposes `evaluate_remediation_policy` as a read-only tool. Agents can ask whether a proposed action would be allowed, blocked, dry-run-only, or approval-required, but they still cannot approve or execute remediation tools.

## Example

```json
{
  "action_type": "restart_deployment",
  "target_namespace": "cascade-targets",
  "target_service": "catalogue",
  "risk_level": "high",
  "blast_radius": 2,
  "rollback_available": true,
  "post_checks_available": true,
  "dry_run": false,
  "approved": false
}
```

At autonomy level 4 this returns `requires_approval`. At level 2 it returns `blocked` for real execution but may return `dry_run_only` when `dry_run=true`.
