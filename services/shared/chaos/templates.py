from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any


def stable_id(prefix: str, seed: str) -> str:
    return f"{prefix}_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]


def experiment_name(experiment_id: str) -> str:
    return experiment_id.replace("_", "-")[:50]


def build_manifest(kind: str, experiment_id: str, namespace: str, service: str, duration_seconds: int) -> dict[str, Any]:
    if kind == "pod_kill":
        return pod_kill_manifest(experiment_id, namespace, service)
    if kind == "network_delay":
        return network_delay_manifest(experiment_id, namespace, service, duration_seconds)
    if kind == "stress_cpu":
        return stress_cpu_manifest(experiment_id, namespace, service, duration_seconds)
    raise ValueError(f"Unsupported chaos kind: {kind}")


def base_metadata(experiment_id: str, namespace: str) -> dict[str, Any]:
    return {
        "name": experiment_name(experiment_id),
        "namespace": namespace,
        "labels": {
            "app.kubernetes.io/part-of": "cascade",
            "cascade.io/phase": "phase7",
            "cascade.io/managed-by": "chaos-executor-service",
            "cascade.io/experiment-id": experiment_id,
        },
        "annotations": {"cascade.io/generated-at": datetime.now(UTC).isoformat()},
    }


def selector(namespace: str, service: str) -> dict[str, Any]:
    return {"namespaces": [namespace], "labelSelectors": {"app": service}}


def pod_kill_manifest(experiment_id: str, namespace: str, service: str) -> dict[str, Any]:
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "PodChaos",
        "metadata": base_metadata(experiment_id, namespace),
        "spec": {"action": "pod-kill", "mode": "one", "selector": selector(namespace, service)},
    }


def network_delay_manifest(experiment_id: str, namespace: str, service: str, duration_seconds: int) -> dict[str, Any]:
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "NetworkChaos",
        "metadata": base_metadata(experiment_id, namespace),
        "spec": {
            "action": "delay",
            "mode": "one",
            "selector": selector(namespace, service),
            "delay": {"latency": "200ms", "correlation": "25", "jitter": "20ms"},
            "duration": f"{duration_seconds}s",
        },
    }


def stress_cpu_manifest(experiment_id: str, namespace: str, service: str, duration_seconds: int) -> dict[str, Any]:
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "StressChaos",
        "metadata": base_metadata(experiment_id, namespace),
        "spec": {
            "mode": "one",
            "selector": selector(namespace, service),
            "stressors": {"cpu": {"workers": 1, "load": 20}},
            "duration": f"{duration_seconds}s",
        },
    }
