from __future__ import annotations

from datetime import UTC, datetime, timedelta


def floor_to_window(value: datetime, window_seconds: int) -> datetime:
    normalized = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    epoch = int(normalized.timestamp())
    floored = epoch - (epoch % window_seconds)
    return datetime.fromtimestamp(floored, tz=UTC)


def window_end(window_start: datetime, window_seconds: int) -> datetime:
    return window_start + timedelta(seconds=window_seconds)

