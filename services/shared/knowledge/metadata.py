from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from services.shared.targets.catalog import ACTIVE_NAMESPACE, ACTIVE_SERVICES

CASCADE_SERVICES = [
    "observation-service",
    "stream-enricher",
    "telemetry-archiver",
    "retrieval-service",
    "feature-extractor-service",
    "anomaly-detector-service",
    "knowledge-ingestion-service",
    "knowledge-retrieval-service",
]
KNOWN_SERVICES = [*ACTIVE_SERVICES, *CASCADE_SERVICES]


def infer_metadata(source_path: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = metadata or {}
    text = content or ""
    lowered = f"{source_path}\n{text}".lower()
    title = metadata.get("title") or _first_markdown_heading(text) or Path(source_path).stem.replace("-", " ").title()
    tags = _tags(metadata.get("tags", []))
    doc_type = metadata.get("document_type") or _document_type(source_path, lowered)
    phase = metadata.get("phase") or _phase(lowered)
    service = metadata.get("service") or _service(lowered)
    namespace = metadata.get("namespace") or (ACTIVE_NAMESPACE if any(s in lowered for s in ACTIVE_SERVICES) else "")
    severity = metadata.get("severity") or _severity(lowered)
    if doc_type and doc_type not in tags:
        tags.append(doc_type)
    if phase and phase not in tags:
        tags.append(phase)
    if service and service not in tags:
        tags.append(service)
    return {
        "title": str(title),
        "document_type": str(doc_type or "note"),
        "phase": str(phase or ""),
        "service": str(service or ""),
        "namespace": str(namespace or ""),
        "severity": str(severity or ""),
        "tags": tags,
        "metadata": {k: v for k, v in metadata.items() if k not in {"title", "document_type", "phase", "service", "namespace", "severity", "tags"}},
    }


def _first_markdown_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


def _document_type(path: str, lowered: str) -> str:
    name = Path(path).name.lower()
    if "runbook" in name or "playbook" in name:
        return "runbook"
    if "incident" in lowered:
        return "incident_report"
    if "anomaly" in lowered:
        return "anomaly_record"
    if "topology" in lowered or "architecture" in lowered:
        return "architecture"
    if name.endswith(".json"):
        return "json"
    return "documentation"


def _phase(lowered: str) -> str:
    match = re.search(r"phase[\s-]*(\d+)", lowered)
    return f"phase-{match.group(1)}" if match else ""


def _service(lowered: str) -> str:
    for service in KNOWN_SERVICES:
        if service in lowered:
            return service
    return ""


def _severity(lowered: str) -> str:
    for severity in ["critical", "high", "medium", "low", "warning", "normal"]:
        if severity in lowered:
            return severity
    return ""


def _tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return []
