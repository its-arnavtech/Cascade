from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field


SchedulerItemType = Literal["chaos_campaign", "autopilot_run"]
SchedulerMode = Literal["disabled", "dry_run_scheduler", "local_demo_scheduler"]
SchedulerDecisionStatus = Literal[
    "evaluated",
    "run_started",
    "skipped",
    "blocked_by_policy",
    "failed",
]


class ScheduledItem(BaseModel):
    item_id: str
    item_type: SchedulerItemType
    target_id: str = ""
    name: str = ""
    schedule: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    paused: bool = False
    mode: SchedulerMode = "dry_run_scheduler"
    next_run_at: str | None = None
    last_run_at: str | None = None
    cooldown_seconds: int = 0
    max_runs_per_window: int = 1
    window_seconds: int = 3600
    failure_count: int = 0
    status: str = "active"
    payload: dict[str, Any] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=lambda: utc_now())


class SchedulerDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: "sched_dec_" + uuid.uuid4().hex[:20])
    item_id: str
    item_type: SchedulerItemType
    target_id: str = ""
    evaluated_at: str = Field(default_factory=lambda: utc_now())
    due_at: str | None = None
    status: SchedulerDecisionStatus
    action: str = ""
    reason: str = ""
    idempotency_key: str = ""
    run_id: str = ""
    dry_run: bool = True
    skipped_missed_windows: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""


class DueEvaluation(BaseModel):
    due: bool
    status: SchedulerDecisionStatus
    reason: str
    idempotency_key: str = ""
    skipped_missed_windows: int = 0
    next_run_at: str | None = None


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.replace("T", " ").replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def schedule_interval_seconds(schedule: dict[str, Any]) -> int | None:
    trigger = str(schedule.get("trigger") or schedule.get("type") or "").lower()
    if trigger in {"", "manual", "disabled"}:
        return None
    if schedule.get("interval_seconds") is not None:
        return max(60, int(schedule["interval_seconds"]))
    if schedule.get("every_minutes") is not None:
        return max(60, int(schedule["every_minutes"]) * 60)
    frequency = str(schedule.get("frequency") or trigger).lower()
    if frequency == "hourly":
        return 3600
    if frequency == "daily":
        return 86400
    return None


def compute_next_run_at(schedule: dict[str, Any], now: datetime | None = None) -> str | None:
    interval = schedule_interval_seconds(schedule)
    if interval is None:
        return None
    base = now or datetime.now(UTC)
    return format_time(base + timedelta(seconds=interval))


def evaluate_due(
    item: ScheduledItem,
    *,
    now: datetime | None = None,
    recent_run_count: int = 0,
    idempotency_seen: bool = False,
) -> DueEvaluation:
    current = now or datetime.now(UTC)
    interval = schedule_interval_seconds(item.schedule)
    if item.mode == "disabled" or not item.enabled:
        return DueEvaluation(due=False, status="skipped", reason="disabled", next_run_at=item.next_run_at)
    if item.paused or item.status.lower() in {"paused", "stopped"}:
        reason = "paused" if item.paused else item.status.lower()
        return DueEvaluation(due=False, status="skipped", reason=reason, next_run_at=item.next_run_at)
    if interval is None:
        return DueEvaluation(due=False, status="skipped", reason="manual_or_unsupported_schedule", next_run_at=item.next_run_at)

    due_at = parse_time(item.next_run_at) or current
    if due_at > current:
        return DueEvaluation(due=False, status="evaluated", reason="not_due", next_run_at=format_time(due_at))
    if item.cooldown_seconds > 0:
        last_run = parse_time(item.last_run_at)
        if last_run and last_run + timedelta(seconds=item.cooldown_seconds) > current:
            return DueEvaluation(due=False, status="skipped", reason="cooldown_active", next_run_at=format_time(last_run + timedelta(seconds=item.cooldown_seconds)))
    if item.max_runs_per_window > 0 and recent_run_count >= item.max_runs_per_window:
        return DueEvaluation(due=False, status="skipped", reason="max_runs_per_window_reached", next_run_at=compute_next_run_at(item.schedule, current))

    key = f"{item.item_id}:{format_time(due_at)}"
    if idempotency_seen:
        return DueEvaluation(due=False, status="skipped", reason="duplicate_due_window", idempotency_key=key, next_run_at=compute_next_run_at(item.schedule, current))

    missed = max(0, int((current - due_at).total_seconds() // interval))
    return DueEvaluation(
        due=True,
        status="evaluated",
        reason="due",
        idempotency_key=key,
        skipped_missed_windows=missed,
        next_run_at=compute_next_run_at(item.schedule, current),
    )


def next_item_after_decision(item: ScheduledItem, evaluation: DueEvaluation, *, success: bool) -> ScheduledItem:
    updated = item.model_copy(deep=True)
    updated.updated_at = utc_now()
    if evaluation.next_run_at:
        updated.next_run_at = evaluation.next_run_at
    if success:
        updated.last_run_at = utc_now()
        updated.failure_count = 0
    elif evaluation.due:
        updated.failure_count += 1
    return updated


def format_time(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
