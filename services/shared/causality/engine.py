from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Any

from services.shared.events.mapping import parse_datetime, stable_json
from services.shared.features.extraction import ch_datetime

SEVERITY_SCORE = {"normal": 0.0, "info": 0.05, "low": 0.25, "medium": 0.5, "warning": 0.55, "high": 0.75, "critical": 1.0}


def analyze_causality(
    feature_windows: list[dict[str, Any]],
    anomalies: list[dict[str, Any]] | None = None,
    topology: dict[str, Any] | None = None,
    *,
    target_service: str | None = None,
    target_feature: str = "error_rate",
    source_feature: str | None = None,
    max_lag_windows: int = 5,
    min_correlation_samples: int = 8,
    min_granger_samples: int = 30,
    granger_max_lag: int = 2,
) -> dict[str, Any]:
    source_feature = source_feature or target_feature
    windows = normalize_feature_windows(feature_windows)
    services = sorted({row["service"] for row in windows if row.get("service")})
    if target_service is None:
        target_service = _target_from_anomalies(anomalies or []) or (services[0] if services else None)
    generated_at = datetime.now(UTC)
    limitations: list[str] = []
    if not target_service:
        limitations.append("No target service was provided and no feature windows were available.")
        return _report(generated_at, None, target_feature, source_feature, [], [], "insufficient_samples", limitations)

    target_series = extract_service_feature_series(windows, target_service, target_feature)
    candidates = []
    anomaly_by_service = anomaly_context_by_service(anomalies or [])
    topology_distances = topology_distance_map(topology, target_service)
    for service in services:
        if service == target_service:
            continue
        source_series = extract_service_feature_series(windows, service, source_feature)
        candidate = analyze_candidate(
            service,
            target_service,
            source_series,
            target_series,
            source_feature,
            target_feature,
            max_lag_windows=max_lag_windows,
            min_correlation_samples=min_correlation_samples,
            min_granger_samples=min_granger_samples,
            granger_max_lag=granger_max_lag,
            topology_distance=topology_distances.get(service),
            anomaly_context=anomaly_by_service.get(service, {}),
        )
        candidates.append(candidate)

    candidates.sort(key=lambda item: (-float(item["rank_score"]), item["best_p_value"] if item["best_p_value"] is not None else 1.0, item["lag_windows"], item["source_service"]))
    for index, candidate in enumerate(candidates, start=1):
        candidate["rank"] = index

    if not target_series:
        limitations.append(f"No feature windows for target service {target_service!r} and feature {target_feature!r}.")
    if not candidates:
        limitations.append("No candidate source services were available for comparison.")
    if candidates and all(candidate["status"] == "insufficient_samples" for candidate in candidates):
        limitations.append("All candidate comparisons had fewer aligned samples than the configured threshold.")
    status = "ranked" if any(candidate["status"] == "ranked" for candidate in candidates) else "insufficient_samples"
    window_bounds = _window_bounds(windows)
    report = _report(generated_at, target_service, target_feature, source_feature, candidates, window_bounds, status, limitations)
    report["summary"] = _summary(report)
    return report


def normalize_feature_windows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        service = str(row.get("service") or row.get("service_name") or "")
        if not service:
            continue
        timestamp = parse_datetime(row.get("window_start") or row.get("observed_at"))
        item = dict(row)
        item["service"] = service
        item["_window_start_dt"] = timestamp
        feature_vector = _json_obj(item.get("feature_vector_json"))
        for key, value in feature_vector.items():
            item.setdefault(key, value)
        normalized.append(item)
    return sorted(normalized, key=lambda item: (item["service"], item["_window_start_dt"]))


def extract_service_feature_series(rows: list[dict[str, Any]], service: str, feature: str) -> list[tuple[datetime, float]]:
    series = []
    for row in rows:
        if row.get("service") != service:
            continue
        value = _float(row.get(feature))
        if value is None:
            continue
        series.append((row["_window_start_dt"], value))
    deduped = {timestamp: value for timestamp, value in series}
    return sorted(deduped.items())


def align_lagged_series(
    source: list[tuple[datetime, float]],
    target: list[tuple[datetime, float]],
    lag_windows: int,
) -> tuple[list[float], list[float]]:
    if not source or not target:
        return [], []
    step = _infer_step_seconds(target) or _infer_step_seconds(source)
    if step is None:
        return [], []
    source_by_time = {timestamp: value for timestamp, value in source}
    x_values: list[float] = []
    y_values: list[float] = []
    offset = timedelta(seconds=step * lag_windows)
    for timestamp, target_value in target:
        source_value = source_by_time.get(timestamp - offset)
        if source_value is None:
            continue
        x_values.append(source_value)
        y_values.append(target_value)
    return x_values, y_values


def analyze_candidate(
    source_service: str,
    target_service: str,
    source_series: list[tuple[datetime, float]],
    target_series: list[tuple[datetime, float]],
    source_feature: str,
    target_feature: str,
    *,
    max_lag_windows: int,
    min_correlation_samples: int,
    min_granger_samples: int,
    granger_max_lag: int,
    topology_distance: int | None,
    anomaly_context: dict[str, Any],
) -> dict[str, Any]:
    lag_results = []
    best: dict[str, Any] | None = None
    for lag in range(max_lag_windows + 1):
        x_values, y_values = align_lagged_series(source_series, target_series, lag)
        sample_count = len(x_values)
        pearson = pearson_correlation(x_values, y_values, min_correlation_samples)
        spearman = spearman_correlation(x_values, y_values, min_correlation_samples)
        result = {
            "lag_windows": lag,
            "sample_count": sample_count,
            "pearson": pearson,
            "spearman": spearman,
        }
        lag_results.append(result)
        effect = max(abs(pearson.get("correlation") or 0.0), abs(spearman.get("correlation") or 0.0))
        p_value = _best_p_value([pearson, spearman])
        if best is None or (p_value if p_value is not None else 1.0, -effect, lag) < (best["p_for_sort"], -best["effect_size"], best["lag_windows"]):
            best = {"lag_windows": lag, "sample_count": sample_count, "pearson": pearson, "spearman": spearman, "effect_size": effect, "best_p_value": p_value, "p_for_sort": p_value if p_value is not None else 1.0}

    best = best or {"lag_windows": 0, "sample_count": 0, "pearson": {}, "spearman": {}, "effect_size": 0.0, "best_p_value": None, "p_for_sort": 1.0}
    granger = granger_causality(source_series, target_series, max_lag=granger_max_lag, min_samples=min_granger_samples)
    status = "ranked" if best["sample_count"] >= min_correlation_samples else "insufficient_samples"
    rank_score = rank_candidate(best, granger, topology_distance, anomaly_context)
    limitations = []
    if status == "insufficient_samples":
        limitations.append(f"Need at least {min_correlation_samples} aligned samples; found {best['sample_count']} at the best lag.")
    if not granger.get("tested"):
        limitations.append(str(granger.get("reason") or "Granger test was not run."))
    return {
        "rank": 0,
        "source_service": source_service,
        "target_service": target_service,
        "source_feature": source_feature,
        "target_feature": target_feature,
        "status": status,
        "rank_score": round(rank_score, 6),
        "best_p_value": best["best_p_value"],
        "effect_size": round(float(best["effect_size"]), 6),
        "lag_windows": best["lag_windows"],
        "sample_count": best["sample_count"],
        "pearson": best["pearson"],
        "spearman": best["spearman"],
        "granger": granger,
        "topology_distance": topology_distance,
        "anomaly_context": anomaly_context,
        "lag_results": lag_results,
        "limitations": limitations,
        "interpretation": _candidate_interpretation(status, source_service, target_service, best, granger),
    }


def pearson_correlation(x_values: list[float], y_values: list[float], min_samples: int) -> dict[str, Any]:
    n = min(len(x_values), len(y_values))
    if n < min_samples:
        return {"tested": False, "reason": f"insufficient_samples: need {min_samples}, found {n}", "sample_count": n, "correlation": None, "p_value": None}
    x = x_values[:n]
    y = y_values[:n]
    r = _pearson_r(x, y)
    if r is None:
        return {"tested": False, "reason": "constant_series", "sample_count": n, "correlation": None, "p_value": None}
    return {"tested": True, "method": "pearson_fisher_z_approx", "sample_count": n, "correlation": r, "p_value": _correlation_p_value(r, n)}


def spearman_correlation(x_values: list[float], y_values: list[float], min_samples: int) -> dict[str, Any]:
    n = min(len(x_values), len(y_values))
    if n < min_samples:
        return {"tested": False, "reason": f"insufficient_samples: need {min_samples}, found {n}", "sample_count": n, "correlation": None, "p_value": None}
    ranked_x = _rank(x_values[:n])
    ranked_y = _rank(y_values[:n])
    r = _pearson_r(ranked_x, ranked_y)
    if r is None:
        return {"tested": False, "reason": "constant_rank_series", "sample_count": n, "correlation": None, "p_value": None}
    return {"tested": True, "method": "spearman_rank_fisher_z_approx", "sample_count": n, "correlation": r, "p_value": _correlation_p_value(r, n)}


def granger_causality(
    source: list[tuple[datetime, float]],
    target: list[tuple[datetime, float]],
    *,
    max_lag: int,
    min_samples: int,
    permutations: int = 99,
) -> dict[str, Any]:
    aligned_source, aligned_target = align_lagged_series(source, target, 0)
    if len(aligned_source) < min_samples:
        return {"tested": False, "reason": f"insufficient_samples: need {min_samples}, found {len(aligned_source)}", "sample_count": len(aligned_source), "p_value": None}
    lag = min(max_lag, max(1, (len(aligned_source) - 2) // 4))
    observed = _granger_f_stat(aligned_source, aligned_target, lag)
    if observed is None:
        return {"tested": False, "reason": "regression_unavailable_or_degenerate", "sample_count": len(aligned_source), "p_value": None}
    rng = random.Random(42)
    null_extreme = 0
    shuffled = list(aligned_source)
    for _ in range(permutations):
        rng.shuffle(shuffled)
        null_stat = _granger_f_stat(shuffled, aligned_target, lag)
        if null_stat is not None and null_stat >= observed:
            null_extreme += 1
    p_value = (null_extreme + 1) / (permutations + 1)
    return {
        "tested": True,
        "method": "lagged_linear_regression_permutation",
        "sample_count": len(aligned_source),
        "lag_order": lag,
        "f_statistic": observed,
        "p_value": p_value,
        "permutations": permutations,
    }


def rank_candidate(best: dict[str, Any], granger: dict[str, Any], topology_distance: int | None, anomaly_context: dict[str, Any]) -> float:
    p_values = [value for value in [best.get("best_p_value"), granger.get("p_value") if granger.get("tested") else None] if value is not None]
    p_score = 1.0 - min(p_values) if p_values else 0.0
    effect_score = min(1.0, abs(float(best.get("effect_size") or 0.0)))
    lag_score = 1.0 / (1.0 + float(best.get("lag_windows") or 0))
    topology_score = 0.0 if topology_distance is None else 1.0 / (1.0 + topology_distance)
    severity_score = float(anomaly_context.get("severity_score") or 0.0)
    return (0.35 * p_score) + (0.30 * effect_score) + (0.15 * lag_score) + (0.10 * topology_score) + (0.10 * severity_score)


def anomaly_context_by_service(anomalies: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    context: dict[str, dict[str, Any]] = {}
    for anomaly in anomalies:
        service = str(anomaly.get("service") or "")
        if not service:
            continue
        severity = str(anomaly.get("severity") or "normal").lower()
        risk = _float(anomaly.get("risk_score")) or SEVERITY_SCORE.get(severity, 0.0)
        score = max(SEVERITY_SCORE.get(severity, 0.0), min(max(risk, 0.0), 1.0))
        current = context.get(service)
        if current is None or score > current["severity_score"]:
            context[service] = {
                "anomaly_id": str(anomaly.get("anomaly_id") or ""),
                "severity": severity,
                "risk_score": risk,
                "severity_score": score,
                "detected_at": str(anomaly.get("detected_at") or ""),
            }
    return context


def topology_distance_map(topology: dict[str, Any] | None, target_service: str) -> dict[str, int]:
    graph = _topology_graph(topology)
    distances = {}
    for source in graph:
        distance = _bfs_distance(graph, source, target_service)
        if distance is not None:
            distances[source] = distance
    return distances


def _topology_graph(topology: dict[str, Any] | None) -> dict[str, set[str]]:
    if not topology:
        return {}
    raw = topology.get("topology_json") if isinstance(topology, dict) else None
    topology_obj = _json_obj(raw) if raw else topology
    dependencies = topology_obj.get("dependencies") or topology_obj.get("topology") or topology_obj.get("edges") or {}
    graph: dict[str, set[str]] = defaultdict(set)
    if isinstance(dependencies, dict):
        for source, targets in dependencies.items():
            if isinstance(targets, list):
                graph[str(source)].update(str(target) for target in targets)
    elif isinstance(dependencies, list):
        for edge in dependencies:
            if not isinstance(edge, dict):
                continue
            source = edge.get("source") or edge.get("from")
            target = edge.get("target") or edge.get("to")
            if source and target:
                graph[str(source)].add(str(target))
    return graph


def _bfs_distance(graph: dict[str, set[str]], source: str, target: str) -> int | None:
    queue: deque[tuple[str, int]] = deque([(source, 0)])
    seen = {source}
    while queue:
        node, distance = queue.popleft()
        if node == target:
            return distance
        for neighbor in graph.get(node, set()):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            queue.append((neighbor, distance + 1))
    return None


def _granger_f_stat(source: list[float], target: list[float], lag: int) -> float | None:
    y, restricted, unrestricted = [], [], []
    for index in range(lag, len(target)):
        y.append(target[index])
        restricted.append([1.0, *[target[index - offset] for offset in range(1, lag + 1)]])
        unrestricted.append([1.0, *[target[index - offset] for offset in range(1, lag + 1)], *[source[index - offset] for offset in range(1, lag + 1)]])
    if len(y) <= len(unrestricted[0]):
        return None
    rss_restricted = _rss(y, restricted)
    rss_unrestricted = _rss(y, unrestricted)
    if rss_restricted is None or rss_unrestricted is None or rss_restricted < rss_unrestricted:
        return None
    q = lag
    denominator_df = len(y) - len(unrestricted[0])
    if denominator_df <= 0:
        return None
    return ((rss_restricted - rss_unrestricted) / q) / (max(rss_unrestricted, 1e-12) / denominator_df)


def _rss(y: list[float], x: list[list[float]]) -> float | None:
    xt = list(zip(*x, strict=False))
    xtx = [[sum(a * b for a, b in zip(col_i, col_j, strict=False)) for col_j in xt] for col_i in xt]
    xty = [sum(a * b for a, b in zip(col, y, strict=False)) for col in xt]
    beta = _solve_linear_system(xtx, xty)
    if beta is None:
        return None
    return sum((actual - sum(coef * value for coef, value in zip(beta, row, strict=False))) ** 2 for actual, row in zip(y, x, strict=False))


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    n = len(vector)
    augmented = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-12:
            return None
        augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        pivot_value = augmented[col][col]
        augmented[col] = [value / pivot_value for value in augmented[col]]
        for row in range(n):
            if row == col:
                continue
            factor = augmented[row][col]
            augmented[row] = [value - factor * augmented[col][idx] for idx, value in enumerate(augmented[row])]
    return [row[-1] for row in augmented]


def _pearson_r(x_values: list[float], y_values: list[float]) -> float | None:
    n = min(len(x_values), len(y_values))
    if n < 2:
        return None
    x = x_values[:n]
    y = y_values[:n]
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    numerator = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=False))
    denom_x = math.sqrt(sum((a - mean_x) ** 2 for a in x))
    denom_y = math.sqrt(sum((b - mean_y) ** 2 for b in y))
    if denom_x == 0.0 or denom_y == 0.0:
        return None
    return max(-1.0, min(1.0, numerator / (denom_x * denom_y)))


def _correlation_p_value(r: float, n: int) -> float | None:
    if n <= 3:
        return None
    bounded = max(-0.999999, min(0.999999, r))
    z = math.atanh(bounded) * math.sqrt(n - 3)
    return math.erfc(abs(z) / math.sqrt(2.0))


def _rank(values: list[float]) -> list[float]:
    ordered = sorted((value, index) for index, value in enumerate(values))
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][0] == ordered[cursor][0]:
            end += 1
        average_rank = (cursor + 1 + end) / 2.0
        for _, index in ordered[cursor:end]:
            ranks[index] = average_rank
        cursor = end
    return ranks


def _infer_step_seconds(series: list[tuple[datetime, float]]) -> int | None:
    if len(series) < 2:
        return None
    deltas = [int((series[index][0] - series[index - 1][0]).total_seconds()) for index in range(1, len(series)) if series[index][0] > series[index - 1][0]]
    return min(deltas) if deltas else None


def _target_from_anomalies(anomalies: list[dict[str, Any]]) -> str | None:
    context = anomaly_context_by_service(anomalies)
    if not context:
        return None
    return max(context.items(), key=lambda item: item[1]["severity_score"])[0]


def _best_p_value(results: list[dict[str, Any]]) -> float | None:
    values = [float(result["p_value"]) for result in results if result.get("p_value") is not None]
    return min(values) if values else None


def _window_bounds(rows: list[dict[str, Any]]) -> list[str]:
    times = [row["_window_start_dt"] for row in rows]
    if not times:
        return []
    return [ch_datetime(min(times)), ch_datetime(max(times))]


def _report(
    generated_at: datetime,
    target_service: str | None,
    target_feature: str,
    source_feature: str,
    candidates: list[dict[str, Any]],
    window_bounds: list[str],
    status: str,
    limitations: list[str],
) -> dict[str, Any]:
    payload = {
        "target_service": target_service or "",
        "target_feature": target_feature,
        "source_feature": source_feature,
        "generated_at": ch_datetime(generated_at),
        "candidate_count": len(candidates),
        "window_bounds": window_bounds,
    }
    return {
        "schema_version": "phase5.causality.v1",
        "report_id": "causal-report-" + hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()[:24],
        "generated_at": ch_datetime(generated_at),
        "target_service": target_service,
        "target_feature": target_feature,
        "source_feature": source_feature,
        "status": status,
        "summary": "",
        "methodology": {
            "correlation": "Lagged Pearson and Spearman correlations with Fisher-z approximate two-sided p-values.",
            "granger": "Lagged linear-regression Granger test with deterministic permutation p-value, run only at or above the configured sample threshold.",
            "ranking": "Weighted score from p-value strength, absolute effect size, lead lag, topology distance, and anomaly severity context.",
        },
        "window_start": window_bounds[0] if window_bounds else None,
        "window_end": window_bounds[1] if window_bounds else None,
        "candidates": candidates,
        "limitations": limitations,
    }


def _summary(report: dict[str, Any]) -> str:
    if report["status"] != "ranked":
        return "Insufficient evidence: aligned telemetry samples are not enough to rank statistical precursor candidates."
    top = report["candidates"][0]
    return (
        f"{top['source_service']} is the highest-ranked statistical precursor for {report['target_service']} "
        f"on {report['target_feature']} at lag {top['lag_windows']} windows. Treat it as ranked evidence for a candidate, not a causal claim."
    )


def _candidate_interpretation(status: str, source: str, target: str, best: dict[str, Any], granger: dict[str, Any]) -> str:
    if status != "ranked":
        return f"{source} could not be assessed against {target}: insufficient aligned samples."
    granger_text = "Granger test not run"
    if granger.get("tested"):
        granger_text = f"Granger p={granger['p_value']:.4g}"
    return f"{source} leads {target} by {best['lag_windows']} windows in the strongest observed association; {granger_text}. Treat as ranked evidence, not a causal claim."


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


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None
