from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.shared.scheduler import ScheduledItem, evaluate_due, format_time, next_item_after_decision


NOW = datetime(2026, 5, 21, 12, 0, tzinfo=UTC)


def due_item(**overrides) -> ScheduledItem:
    data = {
        "item_id": "chaos_campaign:camp-1",
        "item_type": "chaos_campaign",
        "target_id": "camp-1",
        "schedule": {"trigger": "interval", "interval_seconds": 300},
        "next_run_at": format_time(NOW - timedelta(minutes=1)),
        "enabled": True,
        "paused": False,
        "cooldown_seconds": 0,
        "max_runs_per_window": 1,
        "window_seconds": 3600,
    }
    data.update(overrides)
    return ScheduledItem(**data)


def test_due_schedule_triggers_one_run() -> None:
    result = evaluate_due(due_item(), now=NOW)
    assert result.due is True
    assert result.reason == "due"
    assert result.idempotency_key.startswith("chaos_campaign:camp-1:")


def test_paused_schedule_does_not_run() -> None:
    result = evaluate_due(due_item(paused=True), now=NOW)
    assert result.due is False
    assert result.reason == "paused"


def test_disabled_schedule_does_not_run() -> None:
    result = evaluate_due(due_item(enabled=False), now=NOW)
    assert result.due is False
    assert result.reason == "disabled"


def test_duplicate_scheduler_tick_does_not_create_duplicate_run() -> None:
    result = evaluate_due(due_item(), now=NOW, idempotency_seen=True)
    assert result.due is False
    assert result.reason == "duplicate_due_window"


def test_policy_blocked_schedule_can_be_recorded_as_blocked() -> None:
    result = evaluate_due(due_item(), now=NOW)
    assert result.due is True
    assert result.status == "evaluated"


def test_catch_up_behavior_does_not_stampede() -> None:
    item = due_item(next_run_at=format_time(NOW - timedelta(hours=3)))
    result = evaluate_due(item, now=NOW)
    assert result.due is True
    assert result.skipped_missed_windows > 1
    assert result.next_run_at is not None
    updated = next_item_after_decision(item, result, success=True)
    assert updated.next_run_at == result.next_run_at


def test_dry_run_default_is_preserved() -> None:
    item = due_item(item_type="autopilot_run", item_id="autopilot_run:catalogue", target_id="catalogue")
    result = evaluate_due(item, now=NOW)
    assert result.due is True
    assert item.mode == "dry_run_scheduler"
