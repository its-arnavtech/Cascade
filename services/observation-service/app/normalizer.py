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


def build_snapshot_queries(namespace: str) -> dict[str, str]:
    return {
        "cpu": CPU_QUERY_TEMPLATE.format(namespace=namespace),
        "memory": MEMORY_QUERY_TEMPLATE.format(namespace=namespace),
        "restarts": RESTARTS_QUERY_TEMPLATE.format(namespace=namespace),
        "phase": PHASE_QUERY_TEMPLATE.format(namespace=namespace),
    }


def normalize_snapshot(namespace: str, query_results: dict[str, dict[str, Any] | None]) -> SnapshotResponse:
    pods: dict[tuple[str, str], dict[str, Any]] = {}

    _merge_numeric_metric(pods, query_results.get("cpu"), "cpu_usage_cores")
    _merge_numeric_metric(pods, query_results.get("memory"), "memory_working_set_bytes")
    _merge_numeric_metric(pods, query_results.get("restarts"), "restart_count")
    _merge_phase_metric(pods, query_results.get("phase"))

    snapshots = [
        TelemetryPodSnapshot(
            namespace=pod_namespace,
            pod_name=pod_name,
            service_name=_infer_service_name(pod_name),
            pod_phase=values.get("pod_phase"),
            cpu_usage_cores=values.get("cpu_usage_cores"),
            memory_working_set_bytes=values.get("memory_working_set_bytes"),
            restart_count=values.get("restart_count"),
        )
        for (pod_namespace, pod_name), values in sorted(pods.items())
    ]

    return SnapshotResponse(namespace=namespace, timestamp=datetime.now(UTC), pods=snapshots)


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
