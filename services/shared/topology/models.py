from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TopologyNode:
    id: str
    kind: str = "service"
    namespace: str | None = None
    tier: str | None = None
    criticality: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TopologyEdge:
    source: str
    target: str
    relation: str = "depends_on"
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DependencyPath:
    nodes: list[str]
    depth: int
    risk_score: float


@dataclass(frozen=True)
class BlastRadiusResult:
    root_service: str
    affected_services: list[str]
    downstream_services: list[str]
    upstream_services: list[str]
    score: float
    severity: str
    critical_paths: list[DependencyPath]
    formula: str
    graph_source: str = "fallback"
