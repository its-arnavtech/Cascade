from __future__ import annotations

import re
from typing import Any

from .tool_contracts import MUTATING_TOOL_NAMES, TOOL_REGISTRY

SENSITIVE_RE = re.compile(r"(api[_-]?key|token|secret|password|authorization|bearer)\s*[:=]\s*[^,\s}]+", re.IGNORECASE)


def ensure_read_only_tool(tool_name: str) -> None:
    if tool_name in MUTATING_TOOL_NAMES:
        raise ValueError(f"Mutating tool '{tool_name}' is blocked in Phase 6")
    contract = TOOL_REGISTRY.get(tool_name)
    if contract is None:
        raise ValueError(f"Unknown tool '{tool_name}'")
    if not contract.read_only:
        raise ValueError(f"Tool '{tool_name}' is not read-only")


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("<redacted>" if _sensitive_key(k) else redact_sensitive(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value[:100]]
    if isinstance(value, str):
        return SENSITIVE_RE.sub(r"\1=<redacted>", value)
    return value


def _sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in ["password", "secret", "token", "api_key", "apikey", "authorization"])


def text_only_remediation(items: list[str]) -> list[str]:
    safe = []
    for item in items:
        text = str(item).strip()
        if text:
            safe.append(f"SUGGESTION ONLY - human review required: {text}")
    return safe
