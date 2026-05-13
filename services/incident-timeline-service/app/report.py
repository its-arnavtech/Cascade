from __future__ import annotations

from typing import Any


def build_markdown(
    summary: str,
    root_cause: str | None,
    causal_chain: list[str],
    affected_services: list[str],
    evidence: list[dict[str, Any]],
    steps: list[str],
) -> str:
    lines = [
        "# Cascade Incident Report",
        "",
        "## Summary",
        summary,
        "",
        "## Root Cause",
        root_cause or "Unknown",
        "",
        "## Causal Chain",
        " -> ".join(causal_chain) if causal_chain else "No causal chain established.",
        "",
        "## Affected Services",
        ", ".join(affected_services) if affected_services else "No affected services identified.",
        "",
        "## Evidence",
    ]
    if evidence:
        for item in evidence:
            lines.append(f"- {item.get('timestamp')}: {item.get('service')} flags={item.get('anomaly_flags')} status={item.get('derived_status')}")
    else:
        lines.append("- No anomaly evidence captured in the reconstruction window.")

    lines.extend(["", "## Recommended Next Investigation Steps"])
    for step in steps:
        lines.append(f"- {step}")
    return "\n".join(lines)
