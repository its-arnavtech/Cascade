from __future__ import annotations

from dataclasses import asdict
from typing import Any

from services.shared.topology.graph import TopologyGraph

FALLBACK_DEPENDENCIES: dict[str, list[str]] = {
    "front-end": ["catalogue", "carts", "orders", "payment", "user"],
    "catalogue": ["catalogue-db"],
    "catalogue-db": [],
    "carts": ["carts-db"],
    "carts-db": [],
    "orders": ["orders-db", "payment", "shipping", "user"],
    "orders-db": [],
    "payment": [],
    "shipping": ["rabbitmq"],
    "queue-master": ["rabbitmq"],
    "rabbitmq": [],
    "user": ["user-db"],
    "user-db": [],
}

FALLBACK_METADATA: dict[str, dict[str, Any]] = {
    "front-end": {"tier": "edge", "criticality": 1.0},
    "catalogue": {"tier": "catalog", "criticality": 0.8},
    "catalogue-db": {"tier": "data", "criticality": 0.9},
    "carts": {"tier": "shopping", "criticality": 0.8},
    "carts-db": {"tier": "data", "criticality": 0.9},
    "orders": {"tier": "checkout", "criticality": 0.95},
    "orders-db": {"tier": "data", "criticality": 0.9},
    "payment": {"tier": "checkout", "criticality": 0.9},
    "shipping": {"tier": "fulfillment", "criticality": 0.75},
    "queue-master": {"tier": "messaging", "criticality": 0.7},
    "rabbitmq": {"tier": "messaging", "criticality": 0.9},
    "user": {"tier": "identity", "criticality": 0.8},
    "user-db": {"tier": "data", "criticality": 0.9},
}


def _active_catalog_graph() -> TopologyGraph | None:
    try:
        from services.shared.targets.catalog import ACTIVE_DEPENDENCIES, ACTIVE_NAMESPACE, ACTIVE_PROTECTED_SERVICES, ACTIVE_SAFE_CHAOS_SERVICES
    except ImportError:
        return None

    safe_services = set(ACTIVE_SAFE_CHAOS_SERVICES)
    protected_services = set(ACTIVE_PROTECTED_SERVICES)
    metadata = {
        service: {
            "namespace": ACTIVE_NAMESPACE,
            "criticality": 0.9 if service in protected_services else 0.65,
            "protected": service in protected_services,
            "safe_chaos_target": service in safe_services,
        }
        for service in ACTIVE_DEPENDENCIES
    }
    return TopologyGraph.from_dependencies(ACTIVE_DEPENDENCIES, metadata=metadata, source="target-catalog")


def graph() -> TopologyGraph:
    return _active_catalog_graph() or TopologyGraph.from_dependencies(FALLBACK_DEPENDENCIES, metadata=FALLBACK_METADATA, source="fallback")


DEPENDENCIES: dict[str, list[str]] = graph().dependencies()


def downstream(service_name: str) -> list[str]:
    return graph().downstream(service_name)


def upstream(service_name: str) -> list[str]:
    return graph().upstream(service_name)


def impact(root_service: str) -> tuple[list[str], list[str]]:
    return graph().impact(root_service)


def graph_payload() -> dict[str, Any]:
    return graph().to_dict()


def dependencies(service_name: str, hops: int = 2, direction: str = "downstream") -> list[str]:
    return graph().expand(service_name, hops=hops, direction=direction)


def blast_radius(root_service: str, hops: int = 3, depth_cap: int = 4) -> dict[str, Any]:
    result = graph().blast_radius(root_service, hops=hops, depth_cap=depth_cap)
    return {
        **asdict(result),
        "critical_paths": [asdict(path) for path in result.critical_paths],
    }


def critical_paths(root_service: str, depth_cap: int = 4, limit: int = 5) -> dict[str, Any]:
    paths = graph().critical_paths(root_service, depth_cap=depth_cap, limit=limit)
    return {
        "root_service": root_service,
        "depth_cap": depth_cap,
        "critical_paths": [asdict(path) for path in paths],
        "graph_source": graph().source,
    }
