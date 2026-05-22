from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict
from typing import Any, Iterable

from services.shared.topology.models import BlastRadiusResult, DependencyPath, TopologyEdge, TopologyNode


class TopologyGraph:
    """In-memory directed service dependency graph.

    Edges point from caller/service to the dependency it relies on.
    """

    BLAST_RADIUS_FORMULA = (
        "min(1.0, 0.15 + 0.50*downstream_ratio + 0.20*upstream_ratio "
        "+ 0.10*critical_path_ratio + 0.05*avg_criticality)"
    )

    def __init__(self, nodes: Iterable[TopologyNode], edges: Iterable[TopologyEdge], source: str = "fallback") -> None:
        self.source = source
        self.nodes: dict[str, TopologyNode] = {node.id: node for node in nodes}
        self.edges: list[TopologyEdge] = []
        self._outgoing: dict[str, list[str]] = defaultdict(list)
        self._incoming: dict[str, list[str]] = defaultdict(list)

        for edge in edges:
            self.add_node(TopologyNode(id=edge.source))
            self.add_node(TopologyNode(id=edge.target))
            self.edges.append(edge)
            self._outgoing[edge.source].append(edge.target)
            self._incoming[edge.target].append(edge.source)

        for node_id in self.nodes:
            self._outgoing.setdefault(node_id, [])
            self._incoming.setdefault(node_id, [])

        for node_id, neighbors in self._outgoing.items():
            self._outgoing[node_id] = list(dict.fromkeys(neighbors))
        for node_id, neighbors in self._incoming.items():
            self._incoming[node_id] = sorted(dict.fromkeys(neighbors))

    @classmethod
    def from_dependencies(
        cls,
        dependencies: dict[str, list[str]],
        metadata: dict[str, dict[str, Any]] | None = None,
        source: str = "fallback",
    ) -> "TopologyGraph":
        metadata = metadata or {}
        node_ids = set(dependencies)
        for downstream in dependencies.values():
            node_ids.update(downstream)

        nodes = [_node_from_metadata(node_id, metadata.get(node_id, {})) for node_id in sorted(node_ids)]
        edges = [
            TopologyEdge(
                source=source_id,
                target=target_id,
                id=f"{source_id}->{target_id}",
                source_type="static_catalog" if source in {"catalog", "target-catalog"} else "unknown/fallback",
                confidence=0.85 if source in {"catalog", "target-catalog"} else 0.5,
                evidence=f"Dependency edge declared by {source}.",
            )
            for source_id, targets in dependencies.items()
            for target_id in dict.fromkeys(targets)
        ]
        return cls(nodes, edges, source=source)

    @classmethod
    def from_catalog(cls, catalog: dict[str, Any], source: str = "catalog") -> "TopologyGraph":
        dependencies: dict[str, list[str]] = {}
        metadata: dict[str, dict[str, Any]] = {}

        raw_dependencies = catalog.get("dependencies") or catalog.get("topology") or {}
        if isinstance(raw_dependencies, dict):
            dependencies.update({str(service): [str(dep) for dep in deps] for service, deps in raw_dependencies.items()})
        elif isinstance(raw_dependencies, list):
            for item in raw_dependencies:
                if not isinstance(item, dict):
                    continue
                source_id = _first_present(item, ["source", "from", "service", "caller"])
                target_id = _first_present(item, ["target", "to", "dependency", "callee"])
                if source_id and target_id:
                    dependencies.setdefault(str(source_id), []).append(str(target_id))

        for item in catalog.get("services", catalog.get("nodes", [])):
            if not isinstance(item, dict):
                continue
            node_id = _first_present(item, ["id", "name", "service", "service_name"])
            if not node_id:
                continue
            node_id = str(node_id)
            metadata[node_id] = dict(item)
            dependencies.setdefault(node_id, [])
            for dep in item.get("dependencies", item.get("downstream", [])) or []:
                dependencies[node_id].append(str(dep))

        return cls.from_dependencies(dependencies, metadata=metadata, source=source)

    def add_node(self, node: TopologyNode) -> None:
        if node.id not in self.nodes:
            self.nodes[node.id] = node

    def dependencies(self) -> dict[str, list[str]]:
        return {node_id: list(self._outgoing[node_id]) for node_id in sorted(self.nodes)}

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "nodes": [asdict(self.nodes[node_id]) for node_id in sorted(self.nodes)],
            "edges": [asdict(edge) for edge in self.edges],
            "dependencies": self.dependencies(),
        }

    def downstream(self, service_name: str, hops: int = 1) -> list[str]:
        return self.expand(service_name, hops=hops, direction="downstream")

    def upstream(self, service_name: str, hops: int = 1) -> list[str]:
        return self.expand(service_name, hops=hops, direction="upstream")

    def expand(self, service_name: str, hops: int = 1, direction: str = "downstream") -> list[str]:
        max_hops = _bounded_hops(hops)
        adjacency = self._adjacency(direction)
        seen = {service_name}
        ordered: list[str] = []
        queue: deque[tuple[str, int]] = deque([(service_name, 0)])

        while queue:
            current, depth = queue.popleft()
            if depth >= max_hops:
                continue
            for neighbor in adjacency.get(current, []):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                ordered.append(neighbor)
                queue.append((neighbor, depth + 1))

        return ordered

    def critical_paths(self, root_service: str, depth_cap: int = 4, limit: int = 5) -> list[DependencyPath]:
        cap = _bounded_hops(depth_cap)
        if root_service not in self.nodes:
            return []

        paths: list[DependencyPath] = []

        def visit(current: str, path: list[str]) -> None:
            if len(path) - 1 >= cap:
                paths.append(self._path(path))
                return

            next_nodes = [node for node in self._outgoing.get(current, []) if node not in path]
            if not next_nodes:
                paths.append(self._path(path))
                return

            for node in next_nodes:
                visit(node, [*path, node])

        visit(root_service, [root_service])
        return sorted(paths, key=lambda item: (-item.risk_score, -item.depth, item.nodes))[: max(1, limit)]

    def blast_radius(self, root_service: str, hops: int = 3, depth_cap: int = 4) -> BlastRadiusResult:
        downstream = self.downstream(root_service, hops=hops)
        upstream = self.upstream(root_service, hops=hops)
        affected = sorted(dict.fromkeys([*downstream, *upstream]))
        total_other_nodes = max(len(self.nodes) - 1, 1)
        downstream_ratio = len(downstream) / total_other_nodes
        upstream_ratio = len(upstream) / total_other_nodes
        paths = self.critical_paths(root_service, depth_cap=depth_cap)
        critical_path_ratio = (max((path.depth for path in paths), default=0) / max(depth_cap, 1)) if paths else 0.0
        avg_criticality = (
            sum(self.nodes[node].criticality for node in affected if node in self.nodes) / len(affected)
            if affected
            else self.nodes.get(root_service, TopologyNode(root_service)).criticality
        )
        score = min(
            1.0,
            0.15
            + 0.50 * downstream_ratio
            + 0.20 * upstream_ratio
            + 0.10 * critical_path_ratio
            + 0.05 * avg_criticality,
        )
        rounded = round(score, 3)
        return BlastRadiusResult(
            root_service=root_service,
            affected_services=affected,
            downstream_services=downstream,
            upstream_services=upstream,
            score=rounded,
            severity=_severity(rounded),
            critical_paths=paths,
            formula=self.BLAST_RADIUS_FORMULA,
            graph_source=self.source,
        )

    def impact(self, root_service: str) -> tuple[list[str], list[str]]:
        affected = self.downstream(root_service, hops=len(self.nodes))
        return [root_service, *affected], affected

    def _adjacency(self, direction: str) -> dict[str, list[str]]:
        if direction == "downstream":
            return self._outgoing
        if direction == "upstream":
            return self._incoming
        raise ValueError("direction must be 'downstream' or 'upstream'")

    def _path(self, nodes: list[str]) -> DependencyPath:
        criticality = sum(self.nodes[node].criticality for node in nodes if node in self.nodes)
        risk_score = round((len(nodes) - 1) + criticality / max(len(nodes), 1), 3)
        return DependencyPath(nodes=nodes, depth=max(len(nodes) - 1, 0), risk_score=risk_score)


def _bounded_hops(hops: int) -> int:
    return max(0, min(int(hops), 12))


def _node_from_metadata(node_id: str, metadata: dict[str, Any]) -> TopologyNode:
    criticality = metadata.get("criticality", metadata.get("risk", 0.5))
    try:
        criticality_float = max(0.0, min(float(criticality), 1.0))
    except (TypeError, ValueError):
        criticality_float = 0.5
    return TopologyNode(
        id=node_id,
        name=str(metadata.get("name") or node_id),
        kind=str(metadata.get("kind", "service")),
        namespace=metadata.get("namespace"),
        health_status=metadata.get("health_status") or metadata.get("status"),
        source_type=str(metadata.get("source_type") or metadata.get("source") or "static_catalog"),
        confidence=float(metadata.get("confidence", 0.75)),
        last_seen=metadata.get("last_seen"),
        evidence=str(metadata.get("evidence") or "Service declared in topology metadata."),
        tier=metadata.get("tier"),
        criticality=criticality_float,
        metadata={key: value for key, value in metadata.items() if key not in {"id", "name", "service", "service_name"}},
    )


def _first_present(item: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if item.get(key):
            return item[key]
    return None


def _severity(score: float) -> str:
    if score >= 0.75:
        return "critical"
    if score >= 0.5:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"
