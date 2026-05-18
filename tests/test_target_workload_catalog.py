from __future__ import annotations

from pathlib import Path

from services.shared.chaos.schemas import ChaosPlanRequest, SafetyPolicy
from services.shared.remediation.schemas import RemediationPlanRequest, RemediationPolicy
from services.shared.targets.catalog import ACTIVE_TARGET


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
