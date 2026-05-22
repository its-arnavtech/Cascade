from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from services.shared.events.mapping import isoformat, stable_json
from services.shared.targets.catalog import TargetWorkload
from services.shared.topology.models import TopologyEdge, TopologyNode

EDGE_STATIC = "static_catalog"
EDGE_SELECTOR = "kubernetes_selector"
EDGE_OWNER = "kubernetes_owner_reference"
EDGE_TELEMETRY = "telemetry_inferred"
EDGE_TRAFFIC = "traffic_inferred"
EDGE_TRACE = "trace_inferred"
EDGE_UNKNOWN = "unknown/fallback"

DEPENDENCY_RELATION = "depends_on"


def build_discovered_topology(
    target: TargetWorkload,
    *,
    services: list[dict[str, Any]] | None = None,
    deployments: list[dict[str, Any]] | None = None,
    pods: list[dict[str, Any]] | None = None,
    replica_sets: list[dict[str, Any]] | None = None,
    telemetry_events: list[dict[str, Any]] | None = None,
    trace_events: list[dict[str, Any]] | None = None,
    captured_at: datetime | None = None,
    discovery_status: str = "discovered",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Merge static target catalog data with conservative live topology evidence."""

    captured = captured_at or datetime.now(UTC)
    last_seen = isoformat(captured)
    nodes: dict[str, TopologyNode] = {}
    edges: dict[str, TopologyEdge] = {}

    def put_node(node: TopologyNode) -> None:
        existing = nodes.get(node.id)
        if existing is None or (node.confidence, _source_priority(node.source_type)) > (existing.confidence, _source_priority(existing.source_type)):
            nodes[node.id] = node

    def put_edge(edge: TopologyEdge) -> None:
        edge_id = edge.id or _edge_id(edge.source, edge.target, edge.relation, edge.source_type)
        existing = edges.get(edge_id)
        enriched = TopologyEdge(**{**edge.__dict__, "id": edge_id})
        if existing is None or enriched.confidence >= existing.confidence:
            edges[edge_id] = enriched

    put_node(
        TopologyNode(
            id=target.namespace,
            name=target.namespace,
            kind="namespace",
            namespace=target.namespace,
            health_status="unknown",
            source_type=EDGE_STATIC,
            confidence=0.65,
            last_seen=last_seen,
            evidence="Namespace declared by active target catalog.",
        )
    )
    for service in target.services:
        protected = service in target.protected_services
        put_node(
            TopologyNode(
                id=service,
                name=service,
                kind="service",
                namespace=target.namespace,
                health_status="unknown",
                source_type=EDGE_STATIC,
                confidence=0.7,
                last_seen=last_seen,
                evidence="Service declared by active target catalog.",
                criticality=0.9 if protected else 0.65,
                metadata={"protected": protected, "safe_chaos_target": service in target.safe_chaos_services},
            )
        )
    for source, target_service in target.dependency_edges:
        put_edge(
            TopologyEdge(
                source=source,
                target=target_service,
                relation=DEPENDENCY_RELATION,
                namespace=target.namespace,
                source_type=EDGE_STATIC,
                confidence=0.8,
                last_seen=last_seen,
                evidence="Dependency edge declared by active target catalog dependency_edges.",
            )
        )

    service_selectors: dict[str, dict[str, str]] = {}
    for item in services or []:
        metadata = _metadata(item)
        spec = item.get("spec") or {}
        name = _name(metadata)
        if not name:
            continue
        namespace = str(metadata.get("namespace") or target.namespace)
        selector = _string_map(spec.get("selector"))
        service_selectors[name] = selector
        put_node(
            TopologyNode(
                id=name,
                name=name,
                kind="service",
                namespace=namespace,
                health_status="active",
                source_type=EDGE_SELECTOR,
                confidence=0.95,
                last_seen=last_seen,
                evidence=f"Kubernetes Service {namespace}/{name} was discovered.",
                metadata={"labels": _string_map(metadata.get("labels")), "selector": selector},
            )
        )
        put_edge(
            TopologyEdge(
                source=namespace,
                target=name,
                relation="contains",
                namespace=namespace,
                source_type=EDGE_SELECTOR,
                confidence=0.9,
                last_seen=last_seen,
                evidence=f"Service {name} is listed in namespace {namespace}.",
            )
        )

    deployment_selectors: dict[str, dict[str, str]] = {}
    deployment_env_refs: dict[str, set[str]] = defaultdict(set)
    for item in deployments or []:
        metadata = _metadata(item)
        spec = item.get("spec") or {}
        status = item.get("status") or {}
        name = _name(metadata)
        if not name:
            continue
        namespace = str(metadata.get("namespace") or target.namespace)
        selector = _match_labels(spec.get("selector"))
        deployment_selectors[name] = selector
        deployment_env_refs[name].update(_env_service_references(spec, set(target.services) | set(service_selectors)))
        ready = int(status.get("readyReplicas") or 0)
        desired = int(status.get("replicas") or 0)
        health = "healthy" if desired > 0 and ready >= desired else "degraded" if desired else "unknown"
        put_node(
            TopologyNode(
                id=name,
                name=name,
                kind="deployment",
                namespace=namespace,
                health_status=health,
                source_type=EDGE_OWNER,
                confidence=0.95,
                last_seen=last_seen,
                evidence=f"Kubernetes Deployment {namespace}/{name} was discovered with {ready}/{desired} ready replicas.",
                metadata={"labels": _string_map(metadata.get("labels")), "selector": selector, "ready_replicas": ready, "replicas": desired},
            )
        )
        put_edge(
            TopologyEdge(
                source=namespace,
                target=name,
                relation="contains",
                namespace=namespace,
                source_type=EDGE_OWNER,
                confidence=0.9,
                last_seen=last_seen,
                evidence=f"Deployment {name} is listed in namespace {namespace}.",
            )
        )

    replica_set_owner = _replica_set_owner_map(replica_sets or [])
    for item in pods or []:
        metadata = _metadata(item)
        status = item.get("status") or {}
        name = _name(metadata)
        if not name:
            continue
        namespace = str(metadata.get("namespace") or target.namespace)
        labels = _string_map(metadata.get("labels"))
        phase = str(status.get("phase") or "Unknown")
        ready = _pod_ready(status)
        health = "healthy" if phase == "Running" and ready else "degraded" if phase not in {"Running", "Succeeded"} or ready is False else "unknown"
        put_node(
            TopologyNode(
                id=name,
                name=name,
                kind="pod",
                namespace=namespace,
                health_status=health,
                source_type=EDGE_OWNER,
                confidence=0.95,
                last_seen=last_seen,
                evidence=f"Kubernetes Pod {namespace}/{name} was discovered in phase {phase}.",
                metadata={"labels": labels, "phase": phase, "ready": ready, "owner_references": metadata.get("ownerReferences") or []},
            )
        )
        put_edge(
            TopologyEdge(
                source=namespace,
                target=name,
                relation="contains",
                namespace=namespace,
                source_type=EDGE_OWNER,
                confidence=0.85,
                last_seen=last_seen,
                evidence=f"Pod {name} is listed in namespace {namespace}.",
            )
        )
        for service_name, selector in service_selectors.items():
            if selector and _labels_match(selector, labels):
                put_edge(
                    TopologyEdge(
                        source=service_name,
                        target=name,
                        relation="selects_pod",
                        namespace=namespace,
                        source_type=EDGE_SELECTOR,
                        confidence=0.97,
                        last_seen=last_seen,
                        evidence=f"Service selector {_selector_text(selector)} matched pod labels for {name}.",
                    )
                )
        owner_deployment = _pod_owner_deployment(metadata, replica_set_owner)
        if owner_deployment:
            put_edge(
                TopologyEdge(
                    source=owner_deployment,
                    target=name,
                    relation="owns_pod",
                    namespace=namespace,
                    source_type=EDGE_OWNER,
                    confidence=0.98,
                    last_seen=last_seen,
                    evidence=f"Pod ownerReferences resolve to Deployment {owner_deployment}.",
                )
            )
        else:
            for deployment_name, selector in deployment_selectors.items():
                if selector and _labels_match(selector, labels):
                    put_edge(
                        TopologyEdge(
                            source=deployment_name,
                            target=name,
                            relation="owns_pod",
                            namespace=namespace,
                            source_type=EDGE_SELECTOR,
                            confidence=0.82,
                            last_seen=last_seen,
                            evidence=f"Deployment selector {_selector_text(selector)} matched pod labels for {name}.",
                        )
                    )

    for service_name, selector in service_selectors.items():
        for deployment_name, deployment_selector in deployment_selectors.items():
            if selector and deployment_selector and _selectors_overlap(selector, deployment_selector):
                put_edge(
                    TopologyEdge(
                        source=service_name,
                        target=deployment_name,
                        relation="selects_deployment",
                        namespace=target.namespace,
                        source_type=EDGE_SELECTOR,
                        confidence=0.88,
                        last_seen=last_seen,
                        evidence=f"Service selector {_selector_text(selector)} overlaps Deployment selector {_selector_text(deployment_selector)}.",
                    )
                )

    known_services = set(target.services) | set(service_selectors)
    for source, refs in deployment_env_refs.items():
        for ref in sorted(refs):
            if source != ref:
                put_edge(
                    TopologyEdge(
                        source=source,
                        target=ref,
                        relation=DEPENDENCY_RELATION,
                        namespace=target.namespace,
                        source_type=EDGE_UNKNOWN,
                        confidence=0.35,
                        last_seen=last_seen,
                        evidence=f"Kubernetes container environment in {source} references service-like value {ref}; direction is low-confidence.",
                    )
                )

    for edge in _edges_from_telemetry(telemetry_events or [], known_services, last_seen, EDGE_TRAFFIC, 0.62):
        put_edge(edge)
    for edge in _edges_from_telemetry(trace_events or [], known_services, last_seen, EDGE_TRACE, 0.65):
        put_edge(edge)

    dependencies = _service_dependencies(edges.values(), nodes)
    payload = {
        "schema_version": "cascade.topology.v2",
        "snapshot_id": "topology-" + hashlib.sha256(stable_json({"captured_at": last_seen, "nodes": sorted(nodes), "edges": sorted(edges)}).encode("utf-8")).hexdigest()[:24],
        "captured_at": last_seen,
        "source": "live_discovery" if services or deployments or pods else "static_catalog",
        "discovery_status": discovery_status,
        "warnings": warnings or [],
        "namespace": target.namespace,
        "nodes": [node.__dict__ for node in sorted(nodes.values(), key=lambda item: (item.kind, item.id))],
        "edges": [edge.__dict__ for edge in sorted(edges.values(), key=lambda item: (item.source, item.target, item.relation, item.source_type))],
        "dependencies": dependencies,
        "source_summary": _source_summary(nodes.values(), edges.values()),
        "traffic_summary": _traffic_summary(edges.values()),
        "limitations": _limitations(discovery_status, warnings or []),
    }
    return payload


async def discover_from_kubernetes(target: TargetWorkload, *, timeout_seconds: float = 4.0) -> dict[str, Any]:
    try:
        import httpx
    except ImportError:
        return build_discovered_topology(target, discovery_status="static_fallback", warnings=["httpx is not installed; Kubernetes discovery was skipped."])

    token_path = Path(os.getenv("KUBERNETES_SERVICEACCOUNT_TOKEN", "/var/run/secrets/kubernetes.io/serviceaccount/token"))
    ca_path = Path(os.getenv("KUBERNETES_SERVICEACCOUNT_CA", "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"))
    if not token_path.exists():
        return build_discovered_topology(target, discovery_status="static_fallback", warnings=["Kubernetes service account token was not found; using static target catalog."])

    token = token_path.read_text(encoding="utf-8").strip()
    base_url = os.getenv("KUBERNETES_SERVICE_HOST")
    port = os.getenv("KUBERNETES_SERVICE_PORT", "443")
    api_root = f"https://{base_url}:{port}" if base_url else "https://kubernetes.default.svc"
    verify: str | bool = str(ca_path) if ca_path.exists() else True
    headers = {"Authorization": f"Bearer {token}"}
    namespace = target.namespace
    warnings: list[str] = []

    async with httpx.AsyncClient(timeout=timeout_seconds, verify=verify) as client:
        async def get_items(path: str) -> list[dict[str, Any]]:
            try:
                response = await client.get(api_root + path, headers=headers)
                response.raise_for_status()
                payload = response.json()
                return payload.get("items") if isinstance(payload.get("items"), list) else []
            except Exception as exc:
                warnings.append(f"{path} unavailable: {exc.__class__.__name__}")
                return []

        services = await get_items(f"/api/v1/namespaces/{namespace}/services")
        pods = await get_items(f"/api/v1/namespaces/{namespace}/pods")
        deployments = await get_items(f"/apis/apps/v1/namespaces/{namespace}/deployments")
        replica_sets = await get_items(f"/apis/apps/v1/namespaces/{namespace}/replicasets")

    status = "discovered" if any([services, pods, deployments, replica_sets]) else "static_fallback"
    return build_discovered_topology(
        target,
        services=services,
        deployments=deployments,
        pods=pods,
        replica_sets=replica_sets,
        discovery_status=status,
        warnings=warnings,
    )


def service_dependency_graph(topology: dict[str, Any]) -> dict[str, list[str]]:
    dependencies = topology.get("dependencies")
    if isinstance(dependencies, dict):
        return {str(source): [str(target) for target in targets] for source, targets in dependencies.items() if isinstance(targets, list)}
    return _service_dependencies(_edge_objects(topology.get("edges")), _node_map(topology.get("nodes")))


def _edge_objects(value: Any) -> list[TopologyEdge]:
    edges: list[TopologyEdge] = []
    if not isinstance(value, list):
        return edges
    for item in value:
        if isinstance(item, TopologyEdge):
            edges.append(item)
        elif isinstance(item, dict) and item.get("source") and item.get("target"):
            edges.append(
                TopologyEdge(
                    source=str(item["source"]),
                    target=str(item["target"]),
                    relation=str(item.get("relation") or DEPENDENCY_RELATION),
                    source_type=str(item.get("source_type") or EDGE_UNKNOWN),
                    confidence=float(item.get("confidence") or 0.5),
                )
            )
    return edges


def _node_map(value: Any) -> dict[str, TopologyNode]:
    nodes: dict[str, TopologyNode] = {}
    if not isinstance(value, list):
        return nodes
    for item in value:
        if isinstance(item, TopologyNode):
            nodes[item.id] = item
        elif isinstance(item, dict) and item.get("id"):
            nodes[str(item["id"])] = TopologyNode(id=str(item["id"]), kind=str(item.get("kind") or "service"))
    return nodes


def _service_dependencies(edges: Any, nodes: dict[str, TopologyNode]) -> dict[str, list[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for node_id, node in nodes.items():
        if node.kind in {"service", "deployment"}:
            graph.setdefault(node_id, set())
    for edge in edges:
        if edge.relation != DEPENDENCY_RELATION:
            continue
        source_node = nodes.get(edge.source)
        target_node = nodes.get(edge.target)
        if source_node and source_node.kind not in {"service", "deployment"}:
            continue
        if target_node and target_node.kind not in {"service", "deployment"}:
            continue
        graph[edge.source].add(edge.target)
        graph.setdefault(edge.target, set())
    return {source: sorted(targets) for source, targets in sorted(graph.items())}


def _source_summary(nodes: Any, edges: Any) -> dict[str, Any]:
    node_counts: dict[str, int] = defaultdict(int)
    edge_counts: dict[str, int] = defaultdict(int)
    for node in nodes:
        node_counts[node.source_type] += 1
    for edge in edges:
        edge_counts[edge.source_type] += 1
    return {"nodes": dict(sorted(node_counts.items())), "edges": dict(sorted(edge_counts.items()))}


def _source_priority(source_type: str) -> int:
    order = {
        EDGE_TRACE: 6,
        EDGE_TRAFFIC: 6,
        EDGE_TELEMETRY: 5,
        EDGE_SELECTOR: 4,
        EDGE_OWNER: 3,
        EDGE_STATIC: 2,
        EDGE_UNKNOWN: 1,
    }
    return order.get(source_type, 0)


def _limitations(status: str, warnings: list[str]) -> list[str]:
    limitations = []
    if status == "static_fallback":
        limitations.append("Live Kubernetes discovery was unavailable; static target catalog edges are still shown.")
    if warnings:
        limitations.append("Some Kubernetes resources could not be read; confidence may be lower for missing relationships.")
    limitations.append("Dependency direction is only marked high-confidence when a catalog, trace, or clear telemetry signal supports it.")
    return limitations


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("metadata") if isinstance(item.get("metadata"), dict) else {}


def _name(metadata: dict[str, Any]) -> str:
    return str(metadata.get("name") or "")


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if item is not None}


def _match_labels(selector: Any) -> dict[str, str]:
    if not isinstance(selector, dict):
        return {}
    return _string_map(selector.get("matchLabels"))


def _labels_match(selector: dict[str, str], labels: dict[str, str]) -> bool:
    return bool(selector) and all(labels.get(key) == value for key, value in selector.items())


def _selectors_overlap(left: dict[str, str], right: dict[str, str]) -> bool:
    if not left or not right:
        return False
    common = set(left) & set(right)
    return bool(common) and all(left[key] == right[key] for key in common)


def _selector_text(selector: dict[str, str]) -> str:
    return ",".join(f"{key}={value}" for key, value in sorted(selector.items()))


def _replica_set_owner_map(replica_sets: list[dict[str, Any]]) -> dict[str, str]:
    owners: dict[str, str] = {}
    for item in replica_sets:
        metadata = _metadata(item)
        name = _name(metadata)
        if not name:
            continue
        for owner in metadata.get("ownerReferences") or []:
            if owner.get("kind") == "Deployment" and owner.get("name"):
                owners[name] = str(owner["name"])
    return owners


def _pod_owner_deployment(metadata: dict[str, Any], replica_set_owner: dict[str, str]) -> str:
    for owner in metadata.get("ownerReferences") or []:
        kind = owner.get("kind")
        name = str(owner.get("name") or "")
        if kind == "Deployment" and name:
            return name
        if kind == "ReplicaSet" and name in replica_set_owner:
            return replica_set_owner[name]
    return ""


def _pod_ready(status: dict[str, Any]) -> bool | None:
    containers = status.get("containerStatuses")
    if not isinstance(containers, list) or not containers:
        return None
    return all(bool(item.get("ready")) for item in containers if isinstance(item, dict))


def _env_service_references(spec: dict[str, Any], known_services: set[str]) -> set[str]:
    refs: set[str] = set()
    template = spec.get("template") if isinstance(spec.get("template"), dict) else {}
    pod_spec = template.get("spec") if isinstance(template.get("spec"), dict) else {}
    for container in pod_spec.get("containers") or []:
        if not isinstance(container, dict):
            continue
        for env in container.get("env") or []:
            if not isinstance(env, dict):
                continue
            value = str(env.get("value") or "")
            refs.update(_known_service_refs(value, known_services))
    return refs


def _known_service_refs(value: str, known_services: set[str]) -> set[str]:
    refs: set[str] = set()
    tokens = re.split(r"[^A-Za-z0-9_.-]+", value)
    for token in tokens:
        if not token:
            continue
        first = token.split(".", 1)[0]
        if first in known_services:
            refs.add(first)
    return refs


def _edges_from_telemetry(events: list[dict[str, Any]], known_services: set[str], last_seen: str, source_type: str, confidence: float) -> list[TopologyEdge]:
    aggregates: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        source = str(event.get("source_service") or event.get("caller_service") or event.get("service") or "")
        target = str(event.get("target_service") or event.get("dependency_service") or event.get("downstream_service") or "")
        if source in known_services and target in known_services and source != target:
            key = (source, target)
            item = aggregates.setdefault(
                key,
                {
                    "namespace": str(event.get("namespace") or ""),
                    "request_count": 0.0,
                    "error_count": 0.0,
                    "latencies": [],
                    "last_seen": str(event.get("last_seen") or event.get("timestamp") or event.get("observed_at") or last_seen),
                    "evidence_source": str(event.get("evidence_source") or ("trace" if source_type == EDGE_TRACE else "prometheus")),
                    "observation_window": event.get("observation_window") or event.get("window") or event.get("window_id"),
                    "ids": [],
                },
            )
            item["request_count"] += _float(event.get("request_count") or event.get("requests") or event.get("count") or 1.0)
            item["error_count"] += _float(event.get("error_count") or event.get("errors") or 0.0)
            for key_name in ("latency_p50_ms", "latency_p95_ms", "latency_p99_ms", "latency_ms"):
                value = event.get(key_name)
                if value is not None:
                    item["latencies"].append(_float(value))
            item["ids"].append(str(event.get("event_id") or event.get("trace_id") or "unknown"))
            observed = str(event.get("last_seen") or event.get("timestamp") or event.get("observed_at") or "")
            if observed:
                item["last_seen"] = max(str(item["last_seen"]), observed)

    edges: list[TopologyEdge] = []
    for (source, target), item in sorted(aggregates.items()):
        requests = float(item["request_count"])
        errors = float(item["error_count"])
        confidence_score = min(0.95, confidence + min(0.2, requests / 500.0) + (0.05 if item["latencies"] else 0.0))
        avg_latency = sum(item["latencies"]) / len(item["latencies"]) if item["latencies"] else None
        edges.append(
            TopologyEdge(
                source=source,
                target=target,
                relation=DEPENDENCY_RELATION,
                namespace=str(item["namespace"]),
                source_type=source_type,
                confidence=round(confidence_score, 3),
                last_seen=str(item["last_seen"]),
                evidence=(
                    f"{source_type.replace('_', ' ')} evidence observed {source} -> {target}: "
                    f"{requests:g} requests, {errors:g} errors"
                    + (f", avg latency {avg_latency:.1f} ms." if avg_latency is not None else ".")
                ),
                weight=max(1.0, requests),
                metadata={
                    "request_count": requests,
                    "error_count": errors,
                    "error_rate": errors / requests if requests > 0 else None,
                    "avg_latency_ms": avg_latency,
                    "observation_window": item.get("observation_window"),
                    "evidence_source": item["evidence_source"],
                    "sample_ids": item["ids"][:5],
                },
            )
        )
    return edges


def _edge_id(source: str, target: str, relation: str, source_type: str) -> str:
    return f"{source}->{target}:{relation}:{source_type}"


def _traffic_summary(edges: Any) -> dict[str, Any]:
    traffic_edges = [edge for edge in edges if edge.source_type in {EDGE_TRAFFIC, EDGE_TRACE, EDGE_TELEMETRY}]
    return {
        "traffic_inferred_edges": len([edge for edge in traffic_edges if edge.source_type == EDGE_TRAFFIC]),
        "trace_inferred_edges": len([edge for edge in traffic_edges if edge.source_type == EDGE_TRACE]),
        "request_direction_evidence": len(traffic_edges),
        "has_request_direction_evidence": bool(traffic_edges),
    }


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
