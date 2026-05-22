from __future__ import annotations

import hashlib
import json
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

from services.shared.events.mapping import parse_datetime, stable_json
from services.shared.features.extraction import ch_datetime


def build_rca_report(
    feature_windows: list[dict[str, Any]],
    anomalies: list[dict[str, Any]],
    topology: dict[str, Any] | None = None,
    experiments: list[dict[str, Any]] | None = None,
    *,
    target_service: str | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(UTC)
    windows = [_normalize_window(row) for row in feature_windows]
    anomaly_rows = [_normalize_anomaly(row) for row in anomalies]
    graph = _graph(topology)
    topology_evidence = _topology_evidence(topology)
    if not target_service:
        target_service = _target_from_anomalies(anomaly_rows) or _target_from_windows(windows)
    if not target_service:
        return _empty_report(generated_at, "No target service or anomalous telemetry was available.")

    reverse_graph = _reverse_graph(graph)
    candidates = [_candidate(service, windows, anomaly_rows, graph, reverse_graph, target_service, topology_evidence) for service in sorted({row["service"] for row in windows} | {row["service"] for row in anomaly_rows})]
    candidates = [item for item in candidates if item["evidence"]]
    _apply_temporal_precedence(candidates)
    candidates.sort(key=lambda item: (-item["score"], item["first_seen_at"] or "9999", item["service"]))
    root = candidates[0] if candidates else None
    likely = root["service"] if root else target_service
    affected = sorted(set(_related_services(graph, reverse_graph, likely) + [target_service, likely]))
    related_chaos = _related_chaos(experiments or [], likely, target_service, candidates)
    evidence = root["evidence"] if root else []
    timeline = sorted([item for candidate in candidates for item in candidate["timeline"]], key=lambda item: item["timestamp"])[:30]
    limitations = _limitations(candidates, graph, related_chaos)
    confidence = _confidence(root, evidence, graph, related_chaos, limitations)
    status = "ranked" if root and confidence >= 0.35 else "low_confidence" if root else "insufficient_data"
    explanation = _explanation(likely, target_service, affected, evidence, confidence, status)
    payload = {
        "target_service": target_service,
        "likely_root_cause_service": likely,
        "generated_at": ch_datetime(generated_at),
        "evidence": evidence,
        "timeline": timeline,
    }
    return {
        "schema_version": "cascade.rca.v1",
        "report_id": "rca-report-" + hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()[:24],
        "generated_at": ch_datetime(generated_at),
        "status": status,
        "target_service": target_service,
        "likely_root_cause_service": likely,
        "affected_downstream_services": affected,
        "confidence_score": confidence,
        "related_chaos_experiment": related_chaos,
        "evidence": evidence,
        "timeline": timeline,
        "candidate_root_causes": candidates[:10],
        "limitations": limitations,
        "explanation": explanation,
    }


def _candidate(
    service: str,
    windows: list[dict[str, Any]],
    anomalies: list[dict[str, Any]],
    graph: dict[str, set[str]],
    reverse_graph: dict[str, set[str]],
    target: str,
    topology_evidence: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    service_windows = [row for row in windows if row["service"] == service]
    service_anomalies = [row for row in anomalies if row["service"] == service]
    evidence: list[dict[str, Any]] = []
    timeline: list[dict[str, str]] = []
    first_seen: datetime | None = None
    score = 0.0
    for row in service_anomalies:
        first_seen = min(first_seen, row["detected_at"]) if first_seen else row["detected_at"]
        risk = float(row.get("risk_score") or 0.0)
        score += 0.45 * risk
        evidence.append({"type": "anomaly", "id": row.get("anomaly_id", ""), "service": service, "timestamp": ch_datetime(row["detected_at"]), "summary": row.get("explanation", "")})
        timeline.append({"timestamp": ch_datetime(row["detected_at"]), "service": service, "event": "anomaly", "summary": row.get("explanation", "")})
    for row in service_windows:
        reasons = _window_reasons(row)
        if not reasons:
            continue
        observed = row["_time"]
        first_seen = min(first_seen, observed) if first_seen else observed
        score += 0.08 * len(reasons)
        evidence.append({"type": "metric_window", "id": row.get("window_id", ""), "service": service, "timestamp": ch_datetime(observed), "summary": "; ".join(reasons)})
        timeline.append({"timestamp": ch_datetime(observed), "service": service, "event": "metric_window", "summary": "; ".join(reasons)})
    distance = _distance(graph, service, target)
    reverse_distance = _distance(reverse_graph, service, target)
    if service == target:
        score += 0.10
    elif distance is not None or reverse_distance is not None:
        best_distance = min(item for item in [distance, reverse_distance] if item is not None)
        score += 0.25 / max(best_distance, 1)
        if reverse_distance is not None and reverse_distance > 0:
            score += min(0.30, 0.15 * reverse_distance)
    downstream = _downstream(graph, service)
    callers = _downstream(reverse_graph, service)
    if target in downstream or target in callers:
        score += 0.20
    topology_items = _candidate_topology_evidence(service, target, topology_evidence or {})
    evidence.extend(topology_items)
    return {
        "service": service,
        "score": round(min(score, 1.0), 6),
        "first_seen_at": ch_datetime(first_seen) if first_seen else "",
        "topology_distance_to_target": distance,
        "reverse_topology_distance_to_target": reverse_distance,
        "target_is_downstream": target in downstream or target in callers,
        "evidence": evidence[:10],
        "timeline": timeline[:10],
    }


def _window_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    checks = [
        ("error_rate", 0.05),
        ("latency_p95_ms", 750.0),
        ("latency_p99_ms", 1500.0),
        ("restart_rate", 0.1),
        ("unhealthy_rate", 0.2),
        ("warning_event_count", 0.0),
        ("dependency_unhealthy_count", 0.0),
    ]
    for key, threshold in checks:
        value = _float(row.get(key))
        if value > threshold:
            reasons.append(f"{key}={value:.3f}")
    availability = _float(row.get("availability_rate"))
    readiness = _float(row.get("readiness_rate"))
    if availability > 0 and availability < 0.99:
        reasons.append(f"availability_rate={availability:.3f}")
    if readiness > 0 and readiness < 0.99:
        reasons.append(f"readiness_rate={readiness:.3f}")
    if int(row.get("missing_metric_count") or 0) > 0:
        reasons.append("insufficient_data")
    return reasons


def _related_chaos(experiments: list[dict[str, Any]], likely: str, target: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    times = [parse_datetime(item["first_seen_at"]) for item in candidates if item.get("first_seen_at")]
    start = min(times) - timedelta(minutes=10) if times else datetime.now(UTC) - timedelta(minutes=30)
    end = max(times) + timedelta(minutes=10) if times else datetime.now(UTC)
    for event in experiments:
        service = str(event.get("target_service") or event.get("service") or "")
        observed = parse_datetime(event.get("observed_at") or event.get("started_at") or event.get("timestamp"))
        if service in {likely, target} and start <= observed <= end:
            return {
                "experiment_id": str(event.get("experiment_id") or ""),
                "target_service": service,
                "status": str(event.get("status") or ""),
                "observed_at": ch_datetime(observed),
            }
    return None


def _confidence(root: dict[str, Any] | None, evidence: list[dict[str, Any]], graph: dict[str, set[str]], related_chaos: dict[str, Any] | None, limitations: list[str]) -> float:
    if not root:
        return 0.1
    score = min(0.35 + 0.08 * len(evidence), 0.75)
    if root.get("target_is_downstream"):
        score += 0.1
    if graph:
        score += 0.05
    if related_chaos:
        score += 0.05
    if any("insufficient" in item.lower() for item in limitations):
        score = min(score, 0.45)
    if any("red metrics" in item.lower() for item in limitations):
        score = min(score, 0.45)
    if any("request-direction" in item.lower() for item in limitations):
        score = min(score, 0.65)
    return round(max(0.1, min(score, 0.95)), 2)


def _apply_temporal_precedence(candidates: list[dict[str, Any]]) -> None:
    timed = [(parse_datetime(item["first_seen_at"]), item) for item in candidates if item.get("first_seen_at")]
    if not timed:
        return
    earliest = min(observed for observed, _item in timed)
    for observed, item in timed:
        lag_windows = max(0.0, (observed - earliest).total_seconds() / 300.0)
        early_bonus = max(0.0, 0.22 - (0.06 * lag_windows))
        late_penalty = min(0.30, 0.08 * lag_windows)
        item["score"] = round(max(0.0, min(1.0, float(item["score"]) + early_bonus - late_penalty)), 6)
        item["timing_lag_windows_from_first"] = round(lag_windows, 3)


def _limitations(candidates: list[dict[str, Any]], graph: dict[str, set[str]], related_chaos: dict[str, Any] | None) -> list[str]:
    limitations: list[str] = []
    if not candidates:
        limitations.append("Insufficient data: no anomaly or degraded metric windows were available.")
    if not graph:
        limitations.append("No topology graph was available; affected services and root-cause ranking are less reliable.")
    if not related_chaos:
        limitations.append("No overlapping chaos experiment was found.")
    if candidates and len(candidates[0].get("evidence") or []) < 2:
        limitations.append("Evidence is sparse; confidence is intentionally low.")
    if candidates and not _has_red_metric_evidence(candidates):
        limitations.append("RED metrics are missing or partial; confidence is capped instead of inferred.")
    if graph and candidates and not _has_request_direction_evidence(candidates):
        limitations.append("No trace or traffic request-direction evidence was available; topology direction depends on catalog or low-confidence fallback.")
    return limitations


def _explanation(likely: str, target: str, affected: list[str], evidence: list[dict[str, Any]], confidence: float, status: str) -> str:
    if status == "insufficient_data":
        return "Cascade does not have enough anomaly or metric evidence to identify a root cause."
    qualifier = "likely" if confidence >= 0.6 else "possible"
    return f"{likely} is the {qualifier} root-cause service for {target}; evidence includes {len(evidence)} item(s), and topology indicates affected services: {', '.join(affected[:8]) or 'unknown'}."


def _empty_report(generated_at: datetime, reason: str) -> dict[str, Any]:
    payload = {"generated_at": ch_datetime(generated_at), "reason": reason}
    return {
        "schema_version": "cascade.rca.v1",
        "report_id": "rca-report-" + hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()[:24],
        "generated_at": ch_datetime(generated_at),
        "status": "insufficient_data",
        "target_service": "",
        "likely_root_cause_service": "",
        "affected_downstream_services": [],
        "confidence_score": 0.1,
        "related_chaos_experiment": None,
        "evidence": [],
        "timeline": [],
        "candidate_root_causes": [],
        "limitations": [reason],
        "explanation": reason,
    }


def _normalize_window(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    vector = _json_obj(item.get("feature_vector_json"))
    for key, value in vector.items():
        item.setdefault(key, value)
    item["service"] = str(item.get("service") or "unknown")
    item["_time"] = parse_datetime(item.get("window_start") or item.get("window_end"))
    return item


def _normalize_anomaly(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["service"] = str(item.get("service") or "unknown")
    item["detected_at"] = parse_datetime(item.get("detected_at") or item.get("window_start"))
    return item


def _target_from_anomalies(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    return max(rows, key=lambda item: _float(item.get("risk_score")))["service"]


def _target_from_windows(rows: list[dict[str, Any]]) -> str:
    degraded = [(row, len(_window_reasons(row))) for row in rows]
    degraded = [(row, score) for row, score in degraded if score > 0]
    return max(degraded, key=lambda item: item[1])[0]["service"] if degraded else ""


def _graph(topology: dict[str, Any] | None) -> dict[str, set[str]]:
    if not topology:
        return {}
    raw = topology.get("topology_json") if isinstance(topology, dict) else None
    obj = _json_obj(raw) if raw else topology
    dependencies = obj.get("dependencies") or obj.get("topology") or {}
    graph: dict[str, set[str]] = {}
    if isinstance(dependencies, dict):
        for source, targets in dependencies.items():
            graph[str(source)] = {str(target) for target in targets} if isinstance(targets, list) else set()
    for edge in obj.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        if str(edge.get("relation") or "depends_on") != "depends_on":
            continue
        if float(edge.get("confidence") or 0.0) < 0.2:
            continue
        source = edge.get("source") or edge.get("from")
        target = edge.get("target") or edge.get("to")
        if source and target:
            graph.setdefault(str(source), set()).add(str(target))
    return graph


def _topology_evidence(topology: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    if not topology:
        return {}
    raw = topology.get("topology_json") if isinstance(topology, dict) else None
    obj = _json_obj(raw) if raw else topology
    evidence: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in obj.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or edge.get("from") or "")
        target = str(edge.get("target") or edge.get("to") or "")
        if not source or not target:
            continue
        evidence[(source, target)] = {
            "type": "topology_edge",
            "source": source,
            "target": target,
            "source_type": edge.get("source_type") or "unknown/fallback",
            "confidence": edge.get("confidence"),
            "metadata": edge.get("metadata") or {},
            "summary": edge.get("evidence") or f"Topology edge {source} -> {target}",
        }
    return evidence


def _candidate_topology_evidence(service: str, target: str, evidence: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    found = []
    for key in [(service, target), (target, service)]:
        item = evidence.get(key)
        if item:
            found.append(item)
    if not found:
        for (source, dep), item in evidence.items():
            if source == service or dep == service:
                found.append(item)
                if len(found) >= 3:
                    break
    return found[:3]


def _has_red_metric_evidence(candidates: list[dict[str, Any]]) -> bool:
    metric_keys = ("request_rate", "error_rate", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms")
    for candidate in candidates[:3]:
        for item in candidate.get("evidence") or []:
            summary = str(item.get("summary") or "")
            if any(key in summary for key in metric_keys) and "insufficient_data" not in summary:
                return True
    return False


def _has_request_direction_evidence(candidates: list[dict[str, Any]]) -> bool:
    for candidate in candidates[:3]:
        for item in candidate.get("evidence") or []:
            if item.get("source_type") in {"traffic_inferred", "trace_inferred", "telemetry_inferred"}:
                return True
    return False


def _downstream(graph: dict[str, set[str]], service: str) -> list[str]:
    found: list[str] = []
    queue: deque[str] = deque(graph.get(service, set()))
    seen = {service}
    while queue:
        item = queue.popleft()
        if item in seen:
            continue
        seen.add(item)
        found.append(item)
        queue.extend(graph.get(item, set()))
    return found


def _reverse_graph(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = {}
    for source, targets in graph.items():
        reverse.setdefault(source, set())
        for target in targets:
            reverse.setdefault(target, set()).add(source)
    return reverse


def _related_services(graph: dict[str, set[str]], reverse_graph: dict[str, set[str]], service: str) -> list[str]:
    return sorted(set(_downstream(graph, service) + _downstream(reverse_graph, service)))


def _distance(graph: dict[str, set[str]], source: str, target: str) -> int | None:
    if source == target:
        return 0
    queue: deque[tuple[str, int]] = deque([(source, 0)])
    seen = set()
    while queue:
        item, distance = queue.popleft()
        if item in seen:
            continue
        seen.add(item)
        for child in graph.get(item, set()):
            if child == target:
                return distance + 1
            queue.append((child, distance + 1))
    return None


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
