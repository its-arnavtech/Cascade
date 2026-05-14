from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from .safety import text_only_remediation
from .schemas import AgentState


def stable_id(prefix: str, seed: str) -> str:
    return f"{prefix}_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def build_investigation_report(state: AgentState) -> dict[str, Any]:
    service = state.trigger.service or _service_from_evidence(state) or "unknown"
    anomaly_refs = state.anomaly_refs
    knowledge_refs = state.knowledge_evidence
    topology = state.topology_evidence
    telemetry = state.telemetry_evidence
    affected = _affected_services(topology, service)
    suspected = _suspected_root_cause(service, anomaly_refs, telemetry)
    evidence = _evidence_refs(state)
    confidence = min(0.95, 0.25 + 0.12 * len([x for x in [anomaly_refs, knowledge_refs, topology, telemetry] if x]) + 0.03 * min(len(evidence), 5))
    next_steps = [
        "Review cited anomaly and telemetry evidence for the same time window.",
        "Compare upstream and downstream services before planning action.",
        "Use the cited runbook/context pack to prepare a human-reviewed response.",
    ]
    remediation = text_only_remediation([
        f"Consider checking rollout/restart history for {service}.",
        "Consider validating dependency health before restarting any workload.",
        "Prepare rollback or restart commands only after human approval.",
    ])
    summary = f"Cascade investigated {service} using {len(state.tool_call_history)} read-only tool call(s) and found {len(evidence)} evidence reference(s)."
    report_id = stable_id("report", state.investigation_id + json.dumps(evidence, sort_keys=True, default=str))
    markdown = _markdown(state, summary, suspected, affected, evidence, next_steps, remediation, confidence)
    return {
        "report_id": report_id,
        "investigation_id": state.investigation_id,
        "generated_at": _now(),
        "title": f"Investigation Report - {service}",
        "summary": summary,
        "suspected_root_cause": suspected,
        "affected_services": affected,
        "evidence": evidence,
        "timeline": state.timeline_evidence,
        "anomaly_refs": anomaly_refs,
        "knowledge_refs": knowledge_refs,
        "recommended_next_steps": next_steps,
        "suggested_remediation": remediation,
        "confidence": round(confidence, 2),
        "limitations": ["Deterministic Phase 6 mode; no LLM, remediation execution, or Kubernetes mutation was performed."],
        "markdown_report": markdown,
    }


def build_lifecycle_event(event_type: str, state: AgentState, status: str, summary: str = "") -> dict[str, Any]:
    return {
        "schema_version": "phase6.v1",
        "event_type": event_type,
        "investigation_id": state.investigation_id,
        "timestamp": _now_iso(),
        "trigger_type": state.trigger.trigger_type,
        "service": state.trigger.service or "",
        "namespace": state.trigger.namespace,
        "status": status,
        "summary": summary[:500],
        "evidence_refs": _evidence_refs(state)[:10],
        "tools_used": sorted({item.get("tool_name", "") for item in state.tool_call_history if item.get("tool_name")}),
        "confidence": state.confidence,
    }


def _evidence_refs(state: AgentState) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for source, rows in [
        ("anomaly", state.anomaly_refs),
        ("telemetry", state.telemetry_evidence),
        ("topology", state.topology_evidence),
        ("knowledge", state.knowledge_evidence),
        ("incident", state.incident_refs),
    ]:
        for row in rows[:5]:
            refs.append({"source": source, "id": _row_id(row), "summary": _row_summary(row)})
    return refs


def _row_id(row: dict[str, Any]) -> str:
    for key in ["anomaly_id", "event_id", "window_id", "incident_id", "chunk_id", "document_id", "service_name"]:
        if row.get(key):
            return str(row[key])
    return stable_id("evidence", json.dumps(row, sort_keys=True, default=str))[:32]


def _row_summary(row: dict[str, Any]) -> str:
    for key in ["explanation", "summary", "title", "chunk_text", "root_cause_summary", "health_status"]:
        if row.get(key):
            return " ".join(str(row[key]).split())[:300]
    return json.dumps(row, sort_keys=True, default=str)[:300]


def _service_from_evidence(state: AgentState) -> str:
    for rows in [state.anomaly_refs, state.telemetry_evidence, state.incident_refs]:
        for row in rows:
            if row.get("service"):
                return str(row["service"])
            if row.get("root_cause_service"):
                return str(row["root_cause_service"])
    return ""


def _affected_services(topology: list[dict[str, Any]], service: str) -> list[str]:
    affected = [service] if service and service != "unknown" else []
    for row in topology:
        for key in ["affected_services", "downstream", "upstream", "impact_path"]:
            value = row.get(key)
            if isinstance(value, list):
                affected.extend(str(item) for item in value)
    return sorted({item for item in affected if item})


def _suspected_root_cause(service: str, anomalies: list[dict[str, Any]], telemetry: list[dict[str, Any]]) -> str:
    if anomalies:
        top = anomalies[0]
        explanation = top.get("explanation", "")
        return f"{top.get('service', service)} anomaly: {str(explanation)[:300]}"
    if telemetry:
        return f"{service} has recent telemetry requiring operator review."
    return "Insufficient evidence for a root-cause claim."


def _markdown(state: AgentState, summary: str, suspected: str, affected: list[str], evidence: list[dict[str, Any]], next_steps: list[str], remediation: list[str], confidence: float) -> str:
    lines = [
        f"# Investigation Report - {state.trigger.service or 'manual objective'}",
        "",
        f"Objective: {state.trigger.objective}",
        "",
        f"Summary: {summary}",
        "",
        f"Suspected root cause: {suspected}",
        "",
        f"Confidence: {confidence:.2f}",
        "",
        "## Affected Services",
        *(f"- {item}" for item in affected or ["unknown"]),
        "",
        "## Evidence",
        *(f"- [{item['source']}] {item['id']}: {item['summary']}" for item in evidence),
        "",
        "## Recommended Next Steps",
        *(f"- {item}" for item in next_steps),
        "",
        "## Suggested Remediation Ideas",
        *(f"- {item}" for item in remediation),
        "",
        "## Limitations",
        "- Deterministic Phase 6 mode only; suggestions are text-only and require human review.",
    ]
    return "\n".join(lines)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
