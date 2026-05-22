from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.models import SnapshotResponse, TelemetryPodSnapshot


CPU_QUERY_TEMPLATE = (
    'sum(rate(container_cpu_usage_seconds_total{{namespace="{namespace}", pod!="", '
    'container!="POD", container!=""}}[5m])) by (pod, namespace)'
)
MEMORY_QUERY_TEMPLATE = (
    'sum(container_memory_working_set_bytes{{namespace="{namespace}", pod!="", '
    'container!="POD", container!=""}}) by (pod, namespace)'
)
RESTARTS_QUERY_TEMPLATE = (
    'sum(kube_pod_container_status_restarts_total{{namespace="{namespace}"}}) by (pod, namespace)'
)
PHASE_QUERY_TEMPLATE = 'kube_pod_status_phase{{namespace="{namespace}"}}'
READY_QUERY_TEMPLATE = 'kube_pod_status_ready{{namespace="{namespace}", condition="true"}}'
REQUEST_RATE_QUERY_TEMPLATE = 'sum(rate(http_requests_total{{namespace="{namespace}"}}[5m])) by (service, namespace)'
ERROR_RATE_QUERY_TEMPLATE = (
    'sum(rate(http_requests_total{{namespace="{namespace}",status=~"5.."}}[5m])) by (service, namespace) '
    '/ clamp_min(sum(rate(http_requests_total{{namespace="{namespace}"}}[5m])) by (service, namespace), 1)'
)
LATENCY_P50_QUERY_TEMPLATE = 'histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket{{namespace="{namespace}"}}[5m])) by (le, service, namespace)) * 1000'
LATENCY_P95_QUERY_TEMPLATE = 'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{{namespace="{namespace}"}}[5m])) by (le, service, namespace)) * 1000'
LATENCY_P99_QUERY_TEMPLATE = 'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{{namespace="{namespace}"}}[5m])) by (le, service, namespace)) * 1000'


def build_snapshot_queries(namespace: str) -> dict[str, str]:
    return {
        "cpu": CPU_QUERY_TEMPLATE.format(namespace=namespace),
        "memory": MEMORY_QUERY_TEMPLATE.format(namespace=namespace),
        "restarts": RESTARTS_QUERY_TEMPLATE.format(namespace=namespace),
        "phase": PHASE_QUERY_TEMPLATE.format(namespace=namespace),
        "ready": READY_QUERY_TEMPLATE.format(namespace=namespace),
        "request_rate": REQUEST_RATE_QUERY_TEMPLATE.format(namespace=namespace),
        "error_rate": ERROR_RATE_QUERY_TEMPLATE.format(namespace=namespace),
        "latency_p50_ms": LATENCY_P50_QUERY_TEMPLATE.format(namespace=namespace),
        "latency_p95_ms": LATENCY_P95_QUERY_TEMPLATE.format(namespace=namespace),
        "latency_p99_ms": LATENCY_P99_QUERY_TEMPLATE.format(namespace=namespace),
    }


def normalize_snapshot(namespace: str, query_results: dict[str, dict[str, Any] | None], query_status: dict[str, dict[str, Any]] | None = None) -> SnapshotResponse:
    pods: dict[tuple[str, str], dict[str, Any]] = {}

    _merge_numeric_metric(pods, query_results.get("cpu"), "cpu_usage_cores")
    _merge_numeric_metric(pods, query_results.get("memory"), "memory_working_set_bytes")
    _merge_numeric_metric(pods, query_results.get("restarts"), "restart_count")
    _merge_phase_metric(pods, query_results.get("phase"))
    _merge_ready_metric(pods, query_results.get("ready"))
    service_metrics: dict[str, dict[str, Any]] = {}
    for metric_name in ("request_rate", "error_rate", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms"):
        _merge_service_numeric_metric(service_metrics, query_results.get(metric_name), metric_name)
    query_status = query_status or {}
    missing_from_payload = {name for name, payload in query_results.items() if not _vector_results(payload)}
    missing_from_status = {name for name, status in query_status.items() if status.get("status") in {"failed", "empty"}}
    missing_metrics = sorted(missing_from_payload | missing_from_status)
    collection_warnings = [
        f"{name}: {status.get('error') or status.get('warning')}"
        for name, status in sorted(query_status.items())
        if status.get("status") in {"failed", "empty"} and (status.get("error") or status.get("warning"))
    ]
    metric_status = {name: str(status.get("status") or "unknown") for name, status in query_status.items()}
    evidence_quality = _evidence_quality(missing_metrics, query_results)

    snapshots = [
        TelemetryPodSnapshot(
            namespace=pod_namespace,
            pod_name=pod_name,
            service_name=_infer_service_name(pod_name),
            pod_phase=values.get("pod_phase"),
            cpu_usage_cores=values.get("cpu_usage_cores"),
            memory_working_set_bytes=values.get("memory_working_set_bytes"),
            restart_count=values.get("restart_count"),
            ready=values.get("ready"),
            **service_metrics.get(values.get("service_name") or _infer_service_name(pod_name) or "", {}),
            missing_metrics=missing_metrics,
            collection_warnings=collection_warnings,
            metric_status=metric_status,
            evidence_quality=evidence_quality,
        )
        for (pod_namespace, pod_name), values in sorted(pods.items())
    ]

    return SnapshotResponse(
        namespace=namespace,
        timestamp=datetime.now(UTC),
        pods=snapshots,
        query_status=query_status,
        missing_metrics=missing_metrics,
        collection_warnings=collection_warnings,
        used_kubernetes_fallback=False,
    )


def _merge_numeric_metric(
    pods: dict[tuple[str, str], dict[str, Any]],
    payload: dict[str, Any] | None,
    field_name: str,
) -> None:
    for result in _vector_results(payload):
        metric = result.get("metric", {})
        pod_name = metric.get("pod")
        namespace = metric.get("namespace")
        if not pod_name or not namespace:
            continue

        pods.setdefault((namespace, pod_name), {})[field_name] = _parse_prometheus_value(result)


def _merge_phase_metric(pods: dict[tuple[str, str], dict[str, Any]], payload: dict[str, Any] | None) -> None:
    for result in _vector_results(payload):
        metric = result.get("metric", {})
        pod_name = metric.get("pod")
        namespace = metric.get("namespace")
        phase = metric.get("phase")
        if not pod_name or not namespace or not phase:
            continue

        value = _parse_prometheus_value(result)
        pods.setdefault((namespace, pod_name), {})
        if value == 1:
            pods[(namespace, pod_name)]["pod_phase"] = phase


def _merge_ready_metric(pods: dict[tuple[str, str], dict[str, Any]], payload: dict[str, Any] | None) -> None:
    for result in _vector_results(payload):
        metric = result.get("metric", {})
        pod_name = metric.get("pod")
        namespace = metric.get("namespace")
        if not pod_name or not namespace:
            continue
        value = _parse_prometheus_value(result)
        pods.setdefault((namespace, pod_name), {})["ready"] = bool(value == 1)


def _merge_service_numeric_metric(
    service_metrics: dict[str, dict[str, Any]],
    payload: dict[str, Any] | None,
    field_name: str,
) -> None:
    for result in _vector_results(payload):
        metric = result.get("metric", {})
        service_name = _service_metric_name(metric)
        if not service_name:
            continue
        service_metrics.setdefault(service_name, {})[field_name] = _parse_prometheus_value(result)


def _service_metric_name(metric: dict[str, Any]) -> str:
    for key in ("service", "service_name", "kubernetes_service", "app", "app_kubernetes_io_name"):
        value = metric.get(key)
        if value:
            return str(value)
    return ""


def _vector_results(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []

    data = payload.get("data", {})
    if data.get("resultType") != "vector":
        return []

    results = data.get("result", [])
    return results if isinstance(results, list) else []


def _parse_prometheus_value(result: dict[str, Any]) -> float | None:
    value = result.get("value")
    if not isinstance(value, list) or len(value) < 2:
        return None

    try:
        return float(value[1])
    except (TypeError, ValueError):
        return None


def _infer_service_name(pod_name: str) -> str | None:
    if not pod_name:
        return None

    stateful_match = re.match(r"^(?P<name>.+)-\d+$", pod_name)
    if stateful_match:
        return stateful_match.group("name")

    deployment_match = re.match(r"^(?P<name>.+)-[a-f0-9]{8,10}-[a-z0-9]{5}$", pod_name)
    if deployment_match:
        return deployment_match.group("name")

    return pod_name


def _evidence_quality(missing_metrics: list[str], query_results: dict[str, dict[str, Any] | None]) -> str:
    red = {"request_rate", "error_rate", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms"}
    available_red = [name for name in red if _vector_results(query_results.get(name))]
    if len(available_red) >= 4:
        return "red_metrics_available"
    if available_red:
        return "partial_red_metrics"
    if missing_metrics:
        return "insufficient_data"
    return "pod_metrics_available"
