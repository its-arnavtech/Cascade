# Autopilot Closed-Loop Workflow

Autopilot is Cascade's deterministic reliability loop. It connects existing services into one controlled workflow:

```text
detect -> investigate -> bundle evidence -> recommend -> policy check -> dry-run -> approval gate -> apply when allowed -> verify -> record result
```

Autopilot does not replace anomaly detection, agent investigations, remediation planning, approval, or execution. It orchestrates those systems and records what happened.

## Modes

- `read_only`: investigation, evidence, and recommendation only. No dry-run or execution.
- `dry_run`: default. Runs the full loop through policy check and dry-run, then verifies signals without mutating the target workload.
- `local_demo_execute`: still dry-runs first, then requires the existing executor policy, live-demo gates, namespace/service allowlists, and a valid approval record before execution.

Real action execution is blocked by default. Autopilot does not create privileged approvals for itself.

## Run States

Runs move through explicit states:

- `requested`
- `detecting`
- `investigating`
- `evidence_bundled`
- `recommending`
- `policy_checking`
- `dry_running`
- `waiting_for_approval`
- `applying`
- `verifying`
- terminal: `fixed`, `degraded`, `unchanged`, `failed`, or `rolled_back`

`waiting_for_approval` is a safe non-error stop for local demo execution when the plan is not approved. Dry-run runs usually finish as `unchanged` or `degraded` because no mutation occurred.

## API

`autopilot-service` exposes:

- `GET /health`
- `GET /ready`
- `GET /mode`
- `POST /runs`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/evidence`

The Command Center proxy exposes the same surface under `/api/autopilot/*` and allows `POST /api/autopilot/runs`. It does not expose direct mutation endpoints.

Example request:

```json
{
  "trigger_type": "latest_anomaly",
  "service": "catalogue",
  "namespace": "cascade-targets",
  "objective": "Investigate and propose the safest reliability fix",
  "mode": "dry_run",
  "preferred_action_type": "restart_deployment"
}
```

## Storage And Events

Autopilot stores durable run history in ClickHouse when available:

- `autopilot_runs`: latest status and compact run details.
- `autopilot_steps`: append-only state transition records.

For unit tests or degraded local startup it can use an in-memory recorder. Compact lifecycle events are published to Redpanda topic `autopilot.runs` when Kafka is reachable.

## What It Does Not Do Yet

- It is manually/API triggered; it does not continuously consume anomaly topics yet.
- It is deterministic and does not call external LLM APIs.
- It is not production self-healing.
- It does not bypass approval, executor policy, or local demo gates.
- Broad rollback remains executor-dependent; Autopilot records rollback-capable outputs when existing services return them.
