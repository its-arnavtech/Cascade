from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LoadGenerator:
    name: str
    image: str
    target_url: str
    users: int
    spawn_rate: int


@dataclass(frozen=True)
class TargetWorkload:
    name: str
    namespace: str
    frontend_service: str
    services: tuple[str, ...]
    dependency_edges: tuple[tuple[str, str], ...]
    safe_chaos_services: tuple[str, ...]
    protected_services: tuple[str, ...]
    load_generator: LoadGenerator

    @property
    def dependencies(self) -> dict[str, list[str]]:
        graph = {service: [] for service in self.services}
        for upstream, downstream in self.dependency_edges:
            graph.setdefault(upstream, []).append(downstream)
            graph.setdefault(downstream, [])
        return {service: sorted(children) for service, children in graph.items()}


SOCK_SHOP = TargetWorkload(
    name="sock-shop",
    namespace="cascade-targets",
    frontend_service="front-end",
    services=(
        "front-end",
        "catalogue",
        "catalogue-db",
        "carts",
        "carts-db",
        "orders",
        "orders-db",
        "payment",
        "shipping",
        "queue-master",
        "rabbitmq",
        "user",
        "user-db",
    ),
    dependency_edges=(
        ("front-end", "catalogue"),
        ("front-end", "carts"),
        ("front-end", "orders"),
        ("front-end", "payment"),
        ("front-end", "user"),
        ("catalogue", "catalogue-db"),
        ("carts", "carts-db"),
        ("orders", "orders-db"),
        ("orders", "payment"),
        ("orders", "shipping"),
        ("orders", "user"),
        ("queue-master", "rabbitmq"),
        ("shipping", "rabbitmq"),
        ("user", "user-db"),
    ),
    safe_chaos_services=(
        "catalogue",
        "carts",
        "orders",
        "payment",
        "shipping",
        "queue-master",
        "user",
    ),
    protected_services=(
        "front-end",
        "catalogue-db",
        "carts-db",
        "orders-db",
        "rabbitmq",
        "user-db",
    ),
    load_generator=LoadGenerator(
        name="load-test",
        image="curlimages/curl:8.11.1",
        target_url="http://front-end.cascade-targets.svc.cluster.local",
        users=10,
        spawn_rate=2,
    ),
)


def _as_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"target config field '{field}' must be a non-empty string")
    return value.strip()


def _as_string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"target config field '{field}' must be a non-empty list")
    result = tuple(_as_string(item, field) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"target config field '{field}' contains duplicate values")
    return result


def _as_edges(value: Any, services: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise ValueError("target config field 'dependency_edges' must be a list")
    service_names = set(services)
    edges: list[tuple[str, str]] = []
    for item in value:
        if isinstance(item, dict):
            upstream = item.get("from") or item.get("upstream") or item.get("source")
            downstream = item.get("to") or item.get("downstream") or item.get("target")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            upstream, downstream = item
        else:
            raise ValueError("dependency_edges entries must be two-item lists or {from,to} objects")
        edge = (_as_string(upstream, "dependency_edges.from"), _as_string(downstream, "dependency_edges.to"))
        missing = [service for service in edge if service not in service_names]
        if missing:
            raise ValueError(f"dependency edge references unknown service(s): {', '.join(missing)}")
        edges.append(edge)
    return tuple(edges)


def _load_config_payload(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
    else:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("PyYAML is required for CASCADE_TARGET_CONFIG YAML files") from exc
        payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError("target config must be a YAML or JSON object")
    return payload


def load_target_config(path: str | os.PathLike[str]) -> TargetWorkload:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"target config not found: {config_path}")
    payload = _load_config_payload(config_path)
    services = _as_string_tuple(payload.get("services"), "services")
    protected = tuple(_as_string(item, "protected_services") for item in payload.get("protected_services", []))
    safe = tuple(_as_string(item, "safe_chaos_services") for item in payload.get("safe_chaos_services", []))
    unknown_policy_services = sorted((set(protected) | set(safe)) - set(services))
    if unknown_policy_services:
        raise ValueError(f"target config references unknown policy service(s): {', '.join(unknown_policy_services)}")

    load_generator_payload = payload.get("load_generator") or {}
    if not isinstance(load_generator_payload, dict):
        raise ValueError("target config field 'load_generator' must be an object")

    frontend_service = _as_string(payload.get("frontend_service"), "frontend_service")
    if frontend_service not in services:
        raise ValueError("frontend_service must be listed in services")

    return TargetWorkload(
        name=_as_string(payload.get("name"), "name"),
        namespace=_as_string(payload.get("namespace"), "namespace"),
        frontend_service=frontend_service,
        services=services,
        dependency_edges=_as_edges(payload.get("dependency_edges", []), services),
        safe_chaos_services=safe,
        protected_services=protected,
        load_generator=LoadGenerator(
            name=_as_string(load_generator_payload.get("name", "load-generator"), "load_generator.name"),
            image=_as_string(load_generator_payload.get("image", "not-configured"), "load_generator.image"),
            target_url=_as_string(load_generator_payload.get("target_url", f"http://{frontend_service}.{payload.get('namespace')}.svc.cluster.local"), "load_generator.target_url"),
            users=int(load_generator_payload.get("users", 1)),
            spawn_rate=int(load_generator_payload.get("spawn_rate", 1)),
        ),
    )


def _active_target() -> TargetWorkload:
    config_path = os.getenv("CASCADE_TARGET_CONFIG", "").strip()
    if config_path:
        return load_target_config(config_path)
    return SOCK_SHOP


ACTIVE_TARGET = _active_target()
ACTIVE_WORKLOAD_NAME = ACTIVE_TARGET.name
ACTIVE_NAMESPACE = ACTIVE_TARGET.namespace
ACTIVE_FRONTEND_SERVICE = ACTIVE_TARGET.frontend_service
ACTIVE_SERVICES = ACTIVE_TARGET.services
ACTIVE_DEPENDENCIES = ACTIVE_TARGET.dependencies
ACTIVE_SAFE_CHAOS_SERVICES = ACTIVE_TARGET.safe_chaos_services
ACTIVE_PROTECTED_SERVICES = ACTIVE_TARGET.protected_services
ACTIVE_LOAD_GENERATOR = ACTIVE_TARGET.load_generator


def active_service_names(include_protected: bool = True) -> list[str]:
    if include_protected:
        return list(ACTIVE_SERVICES)
    return list(ACTIVE_SAFE_CHAOS_SERVICES)
