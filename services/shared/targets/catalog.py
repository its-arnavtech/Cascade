from __future__ import annotations

from dataclasses import dataclass


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

ACTIVE_TARGET = SOCK_SHOP
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
