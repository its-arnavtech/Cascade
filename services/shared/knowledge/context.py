from __future__ import annotations

import hashlib
from typing import Any


def assemble_context_pack(query: str, results: list[dict[str, Any]], answer_mode: str = "source_grounded") -> dict[str, Any]:
    context_pack_id = "ctx_" + hashlib.sha256((query + "|" + "|".join(str(r.get("chunk_id", "")) for r in results)).encode("utf-8")).hexdigest()[:20]
    if not results:
        return {
            "query": query,
            "context_pack_id": context_pack_id,
            "answer_mode": answer_mode,
            "sources": [],
            "evidence_chunks": [],
            "suggested_context_summary": "No relevant knowledge found for this query.",
            "followup_questions": ["Is there a runbook, incident report, anomaly, or topology snapshot that should be ingested first?"],
            "confidence_hint": "none",
            "limitations": ["No retrieved sources were available; no operational answer was generated."],
        }

    sources = []
    seen = set()
    evidence = []
    for row in results:
        source_key = row.get("document_id")
        if source_key not in seen:
            seen.add(source_key)
            sources.append({
                "document_id": row.get("document_id", ""),
                "title": row.get("title", ""),
                "source_type": row.get("source_type", ""),
                "document_type": row.get("document_type", ""),
                "source_path": row.get("source_path", ""),
                "source_uri": row.get("source_uri", ""),
                "service": row.get("service", ""),
                "namespace": row.get("namespace", ""),
                "severity": row.get("severity", ""),
                "phase": row.get("phase", ""),
            })
        evidence.append({
            "chunk_id": row.get("chunk_id", ""),
            "document_id": row.get("document_id", ""),
            "score": row.get("score", 0.0),
            "title": row.get("title", ""),
            "chunk_text": row.get("chunk_text", ""),
            "metadata": row.get("metadata", {}),
        })
    summary = _deterministic_summary(query, evidence)
    return {
        "query": query,
        "context_pack_id": context_pack_id,
        "answer_mode": answer_mode,
        "sources": sources,
        "evidence_chunks": evidence,
        "suggested_context_summary": summary,
        "followup_questions": _followups(query, evidence),
        "confidence_hint": "medium" if len(evidence) >= 2 else "low",
        "limitations": ["This is source-grounded context assembly only. No LLM or autonomous agent reasoning has been run."],
    }


def _deterministic_summary(query: str, evidence: list[dict[str, Any]]) -> str:
    titles = [str(item.get("title", "")).strip() for item in evidence if item.get("title")]
    unique_titles = []
    for title in titles:
        if title not in unique_titles:
            unique_titles.append(title)
    source_phrase = ", ".join(unique_titles[:3]) if unique_titles else "retrieved operational sources"
    return f"For query '{query}', Cascade found {len(evidence)} evidence chunk(s) from {source_phrase}. Review the cited chunks before deciding on investigation or remediation steps."


def _followups(query: str, evidence: list[dict[str, Any]]) -> list[str]:
    joined = " ".join(str(item.get("chunk_text", "")).lower() for item in evidence)
    questions = []
    if "restart" in query.lower() or "pod" in query.lower() or "restart" in joined:
        questions.append("Which pods restarted, and do telemetry_events or anomaly_events show the same time window?")
    if "latency" in query.lower() or "latency" in joined:
        questions.append("Which upstream and downstream services are adjacent in the latest topology snapshot?")
    if "error" in query.lower() or "error" in joined:
        questions.append("Do feature windows show high error_rate or unhealthy_rate for the affected service?")
    return questions[:3] or ["Which source document or incident report best matches the current service and namespace?"]
