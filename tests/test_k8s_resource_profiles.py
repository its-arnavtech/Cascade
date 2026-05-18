from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
K8S_ROOT = ROOT / "infra" / "kubernetes"
CORE_INFRA_DIRS = {"clickhouse", "qdrant", "redpanda"}
FASTAPI_DEPLOYMENTS = {
    "agent-orchestrator-service",
    "agent-tool-gateway",
    "anomaly-detector-service",
    "approval-service",
    "causal-reconstruction-service",
    "chaos-executor-service",
    "chaos-planner-service",
    "command-center-api",
    "experiment-tracker-service",
    "feature-extractor-service",
    "incident-timeline-service",
    "knowledge-ingestion-service",
    "knowledge-retrieval-service",
    "memory-indexer",
    "observation-service",
    "remediation-executor-service",
    "remediation-recommender-service",
    "retrieval-service",
    "stream-enricher",
    "telemetry-archiver",
    "topology-service",
}


def _load_yaml_documents(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [doc for doc in yaml.safe_load_all(stream) if isinstance(doc, dict)]


def _base_deployments() -> list[tuple[Path, dict[str, Any]]]:
    deployments: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(K8S_ROOT.glob("*/deployment.yaml")):
        for doc in _load_yaml_documents(path):
            if doc.get("kind") == "Deployment":
                deployments.append((path, doc))
    return deployments


def _container_images(doc: dict[str, Any]) -> list[str]:
    pod_spec = doc.get("spec", {}).get("template", {}).get("spec", {})
    return [container.get("image", "") for container in pod_spec.get("containers", [])]


def _is_latest(image: str) -> bool:
    tag = image.rsplit("/", 1)[-1].split(":", 1)
    return len(tag) == 1 or tag[1] == "latest"


def test_every_base_deployment_container_has_cpu_and_memory_requests_and_limits() -> None:
    missing: list[str] = []
    for path, deployment in _base_deployments():
        containers = deployment["spec"]["template"]["spec"].get("containers", [])
        for container in containers:
            resources = container.get("resources", {})
            requests = resources.get("requests", {})
            limits = resources.get("limits", {})
            for resource_type, values in (("requests", requests), ("limits", limits)):
                for key in ("cpu", "memory"):
                    if key not in values:
                        name = deployment["metadata"]["name"]
                        missing.append(f"{path}: {name}/{container.get('name')} missing {resource_type}.{key}")

    assert missing == []


def test_core_infra_images_are_pinned() -> None:
    latest_images: list[str] = []
    for directory in CORE_INFRA_DIRS:
        for path in sorted((K8S_ROOT / directory).glob("*.yaml")):
            for doc in _load_yaml_documents(path):
                template = doc.get("spec", {}).get("template", {})
                pod_spec = template.get("spec", {})
                for container in pod_spec.get("containers", []):
                    image = container.get("image", "")
                    if image and _is_latest(image):
                        latest_images.append(f"{path}: {image}")

    assert latest_images == []


def test_fastapi_deployments_pin_single_worker_default() -> None:
    missing: list[str] = []
    for path, deployment in _base_deployments():
        name = deployment["metadata"]["name"]
        if name not in FASTAPI_DEPLOYMENTS:
            continue
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        env = {item.get("name"): item.get("value") for item in container.get("env", [])}
        if env.get("WEB_CONCURRENCY") != "1":
            missing.append(f"{path}: {name} missing WEB_CONCURRENCY=1")

    assert missing == []


def test_core_infra_has_local_kind_runtime_caps() -> None:
    deployments = {doc["metadata"]["name"]: doc for _, doc in _base_deployments()}

    clickhouse_container = deployments["clickhouse"]["spec"]["template"]["spec"]["containers"][0]
    clickhouse_args = clickhouse_container.get("args", [])
    invalid_clickhouse_runtime_args = {
        "--max_server_memory_usage",
        "--max_thread_pool_size",
        "--background_pool_size",
        "--background_schedule_pool_size",
        "--max_concurrent_queries",
    }
    assert not any(
        str(arg).split("=", maxsplit=1)[0] in invalid_clickhouse_runtime_args for arg in clickhouse_args
    )
    assert clickhouse_container["resources"]["requests"]["memory"] == "512Mi"
    assert clickhouse_container["resources"]["limits"]["memory"] == "1536Mi"

    redpanda_args = deployments["redpanda"]["spec"]["template"]["spec"]["containers"][0].get("args", [])
    assert "--overprovisioned" in redpanda_args
    assert "--smp" in redpanda_args
    assert "768M" in redpanda_args

    qdrant_env = {
        item.get("name"): item.get("value")
        for item in deployments["qdrant"]["spec"]["template"]["spec"]["containers"][0].get("env", [])
    }
    assert qdrant_env["QDRANT__SERVICE__MAX_WORKERS"] == "2"
    assert qdrant_env["QDRANT__STORAGE__PERFORMANCE__MAX_SEARCH_THREADS"] == "2"
    assert qdrant_env["QDRANT__STORAGE__OPTIMIZERS__MAX_OPTIMIZATION_THREADS"] == "1"


def test_low_resource_base_bundle_matches_root_kustomization_resources() -> None:
    root_kustomization = yaml.safe_load((K8S_ROOT / "kustomization.yaml").read_text(encoding="utf-8"))
    expected_parts = [
        (K8S_ROOT / resource).read_text(encoding="utf-8").strip()
        for resource in root_kustomization["resources"]
    ]
    expected = "---\n" + "\n---\n".join(part for part in expected_parts if part) + "\n"

    assert (K8S_ROOT / "base" / "resources.yaml").read_text(encoding="utf-8") == expected
