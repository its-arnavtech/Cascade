from __future__ import annotations

from pathlib import Path

from services.shared.chaos.schemas import ChaosPlanRequest, SafetyPolicy
from services.shared.remediation.schemas import RemediationPlanRequest, RemediationPolicy
from services.shared.targets.catalog import ACTIVE_TARGET, load_target_config


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_ACTIVE_TARGET_TOKENS = (
    "online-boutique",
    "boutique",
    "cartservice",
    "productcatalogservice",
    "checkoutservice",
    "recommendationservice",
    "redis-cart",
)


def test_active_target_is_sock_shop() -> None:
    assert ACTIVE_TARGET.name == "sock-shop"
    assert ACTIVE_TARGET.namespace == "cascade-targets"
    assert ACTIVE_TARGET.frontend_service == "front-end"
    assert "catalogue" in ACTIVE_TARGET.services
    assert "carts" in ACTIVE_TARGET.services
    assert ("front-end", "catalogue") in ACTIVE_TARGET.dependency_edges
    assert ("orders", "payment") in ACTIVE_TARGET.dependency_edges
    assert "catalogue" in ACTIVE_TARGET.safe_chaos_services
    assert "front-end" in ACTIVE_TARGET.protected_services
    assert ACTIVE_TARGET.load_generator.target_url.startswith("http://front-end.")


def test_template_target_config_loads() -> None:
    target = load_target_config(ROOT / "targets" / "template" / "target.yaml")
    assert target.name == "my-app"
    assert target.namespace == "cascade-targets"
    assert target.frontend_service == "my-frontend"
    assert "my-frontend" in target.services
    assert ("my-app-load-generator", "my-frontend") in target.dependency_edges
    assert "my-frontend" in target.safe_chaos_services
    assert "my-app-load-generator" in target.protected_services


def test_template_manifests_are_inactive_and_safe() -> None:
    manifest_root = ROOT / "targets" / "template"
    for name in ("README.md", "kustomization.yaml", "namespace.yaml", "example-app.yaml", "load-generator.example.yaml", "target.yaml"):
        assert (manifest_root / name).exists()
    rendered_source = "\n".join(path.read_text(encoding="utf-8") for path in manifest_root.glob("*.yaml"))
    assert "cascade.io/monitored" in rendered_source
    assert "privileged: true" not in rendered_source
    assert "kind: Secret" not in rendered_source
    assert "password" not in rendered_source.lower()
    assert "token:" not in rendered_source.lower()


def test_active_policies_use_sock_shop_allowlists() -> None:
    assert ChaosPlanRequest().target_service == "catalogue"
    assert ChaosPlanRequest().target_namespace == ACTIVE_TARGET.namespace
    assert RemediationPlanRequest().service == "catalogue"
    assert RemediationPlanRequest().namespace == ACTIVE_TARGET.namespace
    assert SafetyPolicy().allowed_services == list(ACTIVE_TARGET.safe_chaos_services)
    assert RemediationPolicy().allowed_services == list(ACTIVE_TARGET.safe_chaos_services)


def test_sock_shop_manifests_target_cascade_targets_namespace() -> None:
    manifest_root = ROOT / "targets" / "sock-shop"
    assert (manifest_root / "kustomization.yaml").exists()
    rendered_source = "\n".join(path.read_text(encoding="utf-8") for path in manifest_root.glob("*.yaml"))
    assert "cascade-targets" in rendered_source
    assert "namespace: sock-shop" not in rendered_source
    assert "name: front-end" in rendered_source
    assert "name: catalogue" in rendered_source


def test_active_scripts_and_catalog_owned_code_do_not_default_to_online_boutique() -> None:
    active_paths = [
        ROOT / "scripts",
        ROOT / "services" / "shared" / "targets",
        ROOT / "services" / "shared" / "chaos",
        ROOT / "services" / "shared" / "remediation",
        ROOT / "services" / "shared" / "knowledge",
        ROOT / "services" / "chaos-planner-service",
        ROOT / "services" / "remediation-recommender-service",
        ROOT / "services" / "topology-service",
    ]
    offenders: list[str] = []
    for base in active_paths:
        for path in base.rglob("*"):
            if path.suffix.lower() not in {".py", ".ps1", ".yaml", ".yml", ".md"}:
                continue
            text = path.read_text(encoding="utf-8").lower()
            for token in FORBIDDEN_ACTIVE_TARGET_TOKENS:
                if token in text:
                    offenders.append(f"{path.relative_to(ROOT)} contains {token}")
    assert offenders == []
