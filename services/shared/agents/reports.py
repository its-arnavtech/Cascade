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
    blast_radius = state.blast_radius_evidence
    causal_reports = state.causal_report_evidence
    target_workloads = state.target_workload_evidence
    telemetry = state.telemetry_evidence
    affected = _affected_services(topology, service)
    affected = _affected_services(blast_radius, service) if len(_affected_services(blast_radius, service)) > len(affected) else affected
    suspected = _suspected_root_cause(service, anomaly_refs, telemetry)
    evidence = _evidence_refs(state)
    hypothesis = _hypothesis(service, suspected, anomaly_refs, causal_reports)
    supporting_evidence = _supporting_evidence(evidence)
    rejected_alternatives = _rejected_alternatives(service, state)
    confidence, confidence_rationale = _confidence(state, evidence)
    causal_report_summary = _causal_report_summary(causal_reports)
    topology_blast_radius_summary = _topology_blast_radius_summary(blast_radius or topology, affected)
    knowledge_citations = _knowledge_citations(knowledge_refs)
    limitations = _limitations(state)
    next_steps = [
        "Review cited anomaly and telemetry evidence for the same time window.",
        "Compare upstream and downstream services before planning action.",
        "Use the cited runbook/context pack to prepare a human-reviewed response.",
    ]
    recommended_next_action = _recommended_next_action(confidence, evidence, service)
    remediation = text_only_remediation([
        f"Consider checking rollout/restart history for {service}.",
        "Consider validating dependency health before restarting any workload.",
        "Prepare rollback or restart commands only after human approval.",
    ])
    summary = f"Cascade investigated {service} using {len(state.tool_call_history)} read-only tool call(s) and found {len(evidence)} evidence reference(s)."
    report_id = stable_id("report", state.investigation_id + json.dumps(evidence, sort_keys=True, default=str))
    markdown = _markdown(
        state,
        summary,
        suspected,
        affected,
        evidence,
        next_steps,
        remediation,
        confidence,
        hypothesis,
        rejected_alternatives,
        confidence_rationale,
        causal_report_summary,
        topology_blast_radius_summary,
        knowledge_citations,
        limitations,
        recommended_next_action,
    )
    return {
        "report_id": report_id,
        "investigation_id": state.investigation_id,
        "generated_at": _now(),
        "title": f"Investigation Report - {service}",
        "summary": summary,
        "hypothesis": hypothesis,
        "suspected_root_cause": suspected,
        "affected_services": affected,
        "evidence": evidence,
        "supporting_evidence": supporting_evidence,
        "rejected_alternatives": rejected_alternatives,
        "confidence_rationale": confidence_rationale,
        "causal_report_summary": causal_report_summary,
        "topology_blast_radius_summary": topology_blast_radius_summary,
        "knowledge_citations": knowledge_citations,
        "timeline": state.timeline_evidence,
        "anomaly_refs": anomaly_refs,
        "knowledge_refs": knowledge_refs,
        "causal_report_refs": causal_reports,
        "target_workload_refs": target_workloads,
        "recommended_next_steps": next_steps,
        "recommended_next_action": recommended_next_action,
        "suggested_remediation": remediation,
        "confidence": round(confidence, 2),
        "limitations": limitations,
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
        ("blast_radius", state.blast_radius_evidence),
        ("causal_report", state.causal_report_evidence),
        ("target_workload", state.target_workload_evidence),
        ("knowledge", state.knowledge_evidence),
        ("incident", state.incident_refs),
    ]:
        for row in rows[:5]:
            refs.append({"source": source, "id": _row_id(row), "summary": _row_summary(row)})
    return refs


def _row_id(row: dict[str, Any]) -> str:
    for nested_key in ["incident", "blast_radius"]:
        nested = row.get(nested_key)
        if isinstance(nested, dict):
            return _row_id(nested)
    for key in ["anomaly_id", "event_id", "window_id", "incident_id", "chunk_id", "document_id", "service_name", "root_service", "workload"]:
        if row.get(key):
            return str(row[key])
    return stable_id("evidence", json.dumps(row, sort_keys=True, default=str))[:32]


def _row_summary(row: dict[str, Any]) -> str:
    for nested_key in ["incident", "blast_radius"]:
        nested = row.get(nested_key)
        if isinstance(nested, dict):
            return _row_summary(nested)
    for key in ["explanation", "summary", "title", "chunk_text", "root_cause_summary", "health_status", "confidence"]:
        if row.get(key):
            return " ".join(str(row[key]).split())[:300]
    return json.dumps(row, sort_keys=True, default=str)[:300]


def _service_from_evidence(state: AgentState) -> str:
    for rows in [state.anomaly_refs, state.telemetry_evidence, state.target_workload_evidence, state.incident_refs]:
        for row in rows:
            if row.get("service"):
                return str(row["service"])
            if row.get("root_cause_service"):
                return str(row["root_cause_service"])
    return ""


def _affected_services(topology: list[dict[str, Any]], service: str) -> list[str]:
    affected = [service] if service and service != "unknown" else []
    for row in topology:
        blast_radius = row.get("blast_radius")
        if isinstance(blast_radius, dict):
            value = blast_radius.get("affected_services")
            if isinstance(value, list):
                affected.extend(str(item) for item in value)
        for key in ["affected_services", "downstream", "upstream", "impact_path"]:
            value = row.get(key)
            if isinstance(value, list):
                affected.extend(str(item) for item in value)
    return sorted({item for item in affected if item})


def _hypothesis(service: str, suspected: str, anomalies: list[dict[str, Any]], causal_reports: list[dict[str, Any]]) -> str:
    if causal_reports:
        report = causal_reports[0].get("incident", causal_reports[0])
        chain = report.get("causal_chain") if isinstance(report, dict) else None
        if isinstance(chain, list) and chain:
            return f"{service} degradation is plausibly connected to causal chain: {' -> '.join(str(item) for item in chain[:6])}."
    if anomalies:
        return f"{service} is the leading hypothesis because anomaly evidence aligns with the investigation objective."
    if suspected != "Insufficient evidence for a root-cause claim.":
        return suspected
    return "No root-cause hypothesis is asserted because the available evidence is insufficient."


def _supporting_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source": item["source"],
            "id": item["id"],
            "supports": item["summary"],
        }
        for item in evidence
    ]


def _rejected_alternatives(service: str, state: AgentState) -> list[dict[str, str]]:
    rejected: list[dict[str, str]] = []
    if state.topology_evidence or state.blast_radius_evidence:
        rejected.append({
            "alternative": "Unbounded topology-wide incident",
            "reason": "Topology evidence was consulted; affected services are limited to the cited blast-radius data.",
        })
    if state.knowledge_evidence:
        rejected.append({
            "alternative": "No applicable operating context exists",
            "reason": "Knowledge retrieval returned cited runbook or incident context.",
        })
    if not rejected:
        rejected.append({
            "alternative": f"Specific alternate cause for {service}",
            "reason": "Not rejected; no independent evidence was available to rule out alternatives.",
        })
    return rejected


def _confidence(state: AgentState, evidence: list[dict[str, Any]]) -> tuple[float, str]:
    evidence_groups = {
        "anomaly": bool(state.anomaly_refs),
        "telemetry": bool(state.telemetry_evidence),
        "topology/blast-radius": bool(state.topology_evidence or state.blast_radius_evidence),
        "causal": bool(state.causal_report_evidence),
        "knowledge": bool(state.knowledge_evidence),
        "incident-history": bool(state.incident_refs),
        "target-workload": bool(state.target_workload_evidence),
    }
    present = [name for name, available in evidence_groups.items() if available]
    missing = [name for name, available in evidence_groups.items() if not available]
    if not evidence:
        return 0.15, "Low confidence: no cited evidence was collected, so the report makes no root-cause claim."
    confidence = min(0.95, 0.18 + 0.09 * len(present) + 0.025 * min(len(evidence), 8))
    if "anomaly" not in present and "telemetry" not in present:
        confidence = min(confidence, 0.42)
    if "topology/blast-radius" not in present:
        confidence = min(confidence, 0.55)
    rationale = f"Confidence reflects {len(evidence)} cited evidence item(s) across {', '.join(present)}."
    if missing:
        rationale += f" Missing evidence lowers confidence for: {', '.join(missing)}."
    return confidence, rationale


def _causal_report_summary(causal_reports: list[dict[str, Any]]) -> str:
    if not causal_reports:
        return "No causal report was available; statistical precursor evidence is unavailable."
    report = causal_reports[0].get("incident", causal_reports[0])
    if not isinstance(report, dict):
        return "Causal reconstruction returned an unreadable report shape."
    root = report.get("root_cause_service") or "unknown"
    chain = report.get("causal_chain") or []
    affected = report.get("affected_services") or []
    confidence = report.get("confidence") or "unknown"
    chain_text = " -> ".join(str(item) for item in chain[:6]) if isinstance(chain, list) and chain else "none cited"
    affected_text = ", ".join(str(item) for item in affected[:8]) if isinstance(affected, list) and affected else "none cited"
    return f"Causal report root={root}, confidence={confidence}, chain={chain_text}, affected={affected_text}."


def _topology_blast_radius_summary(blast_rows: list[dict[str, Any]], affected: list[str]) -> str:
    if not blast_rows:
        return "No topology or blast-radius evidence was available."
    first = blast_rows[0].get("blast_radius", blast_rows[0])
    if not isinstance(first, dict):
        first = {}
    root = first.get("root_service") or blast_rows[0].get("root_service") or "unknown"
    path = first.get("impact_path") or blast_rows[0].get("impact_path") or []
    affected_services = first.get("affected_services") or blast_rows[0].get("affected_services") or affected
    path_text = " -> ".join(str(item) for item in path[:8]) if isinstance(path, list) and path else "none cited"
    affected_text = ", ".join(str(item) for item in affected_services[:10]) if isinstance(affected_services, list) and affected_services else "unknown"
    return f"Blast-radius root={root}; impact path={path_text}; affected services={affected_text}."


def _knowledge_citations(knowledge_refs: list[dict[str, Any]]) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    for row in knowledge_refs[:8]:
        citations.append({
            "chunk_id": str(row.get("chunk_id") or _row_id(row)),
            "title": str(row.get("title") or row.get("document_id") or "Knowledge source"),
            "source_uri": str(row.get("source_uri") or row.get("source_path") or ""),
            "excerpt": _row_summary(row),
        })
    return citations


def _limitations(state: AgentState) -> list[str]:
    limitations = ["Deterministic Phase 6 mode; no LLM, remediation execution, chaos execution, or Kubernetes mutation was performed."]
    if not state.anomaly_refs and not state.telemetry_evidence:
        limitations.append("No anomaly or telemetry evidence was available for the target time window.")
    if not state.causal_report_evidence:
        limitations.append("No causal report was available; statistical precursor evidence is unavailable for this investigation.")
    if not state.topology_evidence and not state.blast_radius_evidence:
        limitations.append("No topology or blast-radius evidence was available to bound impact.")
    if not state.knowledge_evidence:
        limitations.append("No knowledge citations were available for runbook or prior-incident context.")
    failed_tools = [item for item in state.tool_call_history if item.get("status") == "error"]
    for item in failed_tools[:6]:
        tool = item.get("tool_name") or "unknown_tool"
        error = item.get("error") or "upstream unavailable"
        limitations.append(f"Read-only tool {tool} was unavailable or returned no usable evidence: {error}")
    return limitations


def _recommended_next_action(confidence: float, evidence: list[dict[str, Any]], service: str) -> str:
    if confidence < 0.5 or not evidence:
        return f"Collect anomaly, telemetry, topology, and causal evidence for {service} before planning any operational action."
    return f"Have an operator review the cited evidence for {service} and choose a human-approved response plan."


def _suspected_root_cause(service: str, anomalies: list[dict[str, Any]], telemetry: list[dict[str, Any]]) -> str:
    if anomalies:
        top = anomalies[0]
        explanation = top.get("explanation", "")
        return f"{top.get('service', service)} anomaly: {str(explanation)[:300]}"
    if telemetry:
        return f"{service} has recent telemetry requiring operator review."
    return "Insufficient evidence for a root-cause claim."


def _markdown(
    state: AgentState,
    summary: str,
    suspected: str,
    affected: list[str],
    evidence: list[dict[str, Any]],
    next_steps: list[str],
    remediation: list[str],
    confidence: float,
    hypothesis: str,
    rejected_alternatives: list[dict[str, str]],
    confidence_rationale: str,
    causal_report_summary: str,
    topology_blast_radius_summary: str,
    knowledge_citations: list[dict[str, str]],
    limitations: list[str],
    recommended_next_action: str,
) -> str:
    lines = [
        f"# Investigation Report - {state.trigger.service or 'manual objective'}",
        "",
        f"Objective: {state.trigger.objective}",
        "",
        f"Summary: {summary}",
        "",
        f"Hypothesis: {hypothesis}",
        "",
        f"Suspected root cause: {suspected}",
        "",
        f"Confidence: {confidence:.2f}",
        "",
        f"Confidence rationale: {confidence_rationale}",
        "",
        f"Causal report summary: {causal_report_summary}",
        "",
        f"Topology blast-radius summary: {topology_blast_radius_summary}",
        "",
        "## Affected Services",
        *(f"- {item}" for item in affected or ["unknown"]),
        "",
        "## Evidence",
        *(f"- [{item['source']}] {item['id']}: {item['summary']}" for item in evidence or [{"source": "none", "id": "none", "summary": "No evidence collected."}]),
        "",
        "## Rejected Alternatives",
        *(f"- {item['alternative']}: {item['reason']}" for item in rejected_alternatives),
        "",
        "## Knowledge Citations",
        *(f"- {item['chunk_id']} {item['title']}: {item['excerpt']}" for item in knowledge_citations or [{"chunk_id": "none", "title": "No citation", "excerpt": "No knowledge citation available."}]),
        "",
        "## Recommended Next Steps",
        *(f"- {item}" for item in next_steps),
        "",
        f"Recommended next action: {recommended_next_action}",
        "",
        "## Suggested Remediation Ideas",
        *(f"- {item}" for item in remediation),
        "",
        "## Limitations",
        *(f"- {item}" for item in limitations),
    ]
    return "\n".join(lines)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
