from __future__ import annotations


DEPENDENCIES: dict[str, list[str]] = {
    "frontend": ["cartservice", "checkoutservice", "productcatalogservice", "currencyservice", "recommendationservice", "adservice"],
    "cartservice": ["redis-cart"],
    "checkoutservice": ["cartservice", "productcatalogservice", "currencyservice", "paymentservice", "shippingservice", "emailservice"],
    "productcatalogservice": [],
    "currencyservice": [],
    "paymentservice": [],
    "shippingservice": [],
    "emailservice": [],
    "recommendationservice": ["productcatalogservice"],
    "adservice": [],
    "redis-cart": [],
}


def downstream(service_name: str) -> list[str]:
    return DEPENDENCIES.get(service_name, [])


def upstream(service_name: str) -> list[str]:
    return sorted(service for service, deps in DEPENDENCIES.items() if service_name in deps)


def impact(root_service: str) -> tuple[list[str], list[str]]:
    seen: set[str] = set()
    ordered: list[str] = []

    def visit(service: str) -> None:
        for child in DEPENDENCIES.get(service, []):
            if child in seen:
                continue
            seen.add(child)
            ordered.append(child)
            visit(child)

    visit(root_service)
    return [root_service, *ordered], ordered
