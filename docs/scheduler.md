# Cascade Scheduler

Cascade now includes an always-on scheduler service for recurring chaos campaigns and Autopilot dry-runs.

The scheduler is a coordinator, not an executor. It evaluates persisted schedules, records a scheduler decision, emits an audit event, and then calls the existing subsystem API:

- Chaos campaigns: `POST /campaigns/{campaign_id}/start` with `dry_run=true`, `approved=false`, and `requested_by=scheduler-service`.
- Autopilot: `POST /runs` with `mode=dry_run` or `mode=read_only`.

Real chaos and real remediation are not available through the default scheduler path. Local-demo execution still requires the existing policy gates, approval checks, and service allowlists.

## Scheduling Rules

Supported schedule forms are intentionally small:

- `{ "trigger": "interval", "interval_seconds": 300 }`
- `{ "trigger": "interval", "every_minutes": 5 }`
- `{ "trigger": "hourly" }` or `{ "frequency": "hourly" }`
- `{ "trigger": "daily" }` or `{ "frequency": "daily" }`

Each scheduled item stores `next_run_at`, `last_run_at`, `enabled`, `paused`, `failure_count`, `cooldown_seconds`, `max_runs_per_window`, and `window_seconds`.

If Cascade was down for multiple schedule windows, the scheduler starts at most one catch-up run and records `skipped_missed_windows` in the decision history.

## Decisions And Auditing

Scheduler decisions are written to `scheduler_decisions` with explicit statuses:

- `evaluated`
- `run_started`
- `skipped`
- `blocked_by_policy`
- `failed`

Audit events use `system/deployment` with `schedule.*` event types so later product wiring can connect scheduler decisions to chaos campaign runs, Autopilot runs, policy blocks, and operational history.

## API Surface

- `GET /scheduler/status`
- `GET /scheduler/items`
- `POST /scheduler/items`
- `POST /scheduler/items/{item_id}/enable`
- `POST /scheduler/items/{item_id}/disable`
- `POST /scheduler/items/{item_id}/pause`
- `POST /scheduler/items/{item_id}/resume`
- `POST /scheduler/items/{item_id}/run`
- `GET /scheduler/history`

Command Center exposes these through `/api/scheduler/...` and keeps the default proxy gate restricted to dry-run scheduler modes.
