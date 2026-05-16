from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def is_approval_current(row: dict[str, Any] | None) -> bool:
    if not row or row.get("decision") != "approved":
        return False
    expires_at = row.get("expires_at")
    if not expires_at:
        return True
    try:
        return datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")).astimezone(UTC) > datetime.now(UTC)
    except Exception:
        return True

