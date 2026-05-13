from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any


def _json_default(value: Any) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def serialize_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, default=_json_default, separators=(",", ":"), sort_keys=True).encode("utf-8")


def deserialize_json(payload: bytes) -> dict[str, Any]:
    decoded = json.loads(payload.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Kafka message payload must decode to a JSON object")
    return decoded
