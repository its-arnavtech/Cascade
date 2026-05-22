from __future__ import annotations

import importlib.util
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from services.shared.audit import REDACTED, redact
from services.shared.security.approval import approval_metadata, approval_valid_for_plan, plan_hash


ROOT = Path(__file__).resolve().parents[1]


class FakeAIOKafkaProducer:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_and_wait(self, *args: Any, **kwargs: Any) -> Any:
        return types.SimpleNamespace(topic="test", partition=0, offset=0)


sys.modules.setdefault("aiokafka", types.SimpleNamespace(AIOKafkaProducer=FakeAIOKafkaProducer))


class FakeApiException(Exception):
    status = 500


class FakeKubernetesApi:
    def __getattr__(self, name: str):
        def _call(*args: Any, **kwargs: Any) -> Any:
            return types.SimpleNamespace(items=[])

        return _call


fake_kubernetes_client = types.SimpleNamespace(
    ApiException=FakeApiException,
    AppsV1Api=lambda: FakeKubernetesApi(),
    CoreV1Api=lambda: FakeKubernetesApi(),
    CustomObjectsApi=lambda: FakeKubernetesApi(),
)
fake_kubernetes_config = types.SimpleNamespace(
    load_incluster_config=lambda: None,
    list_kube_config_contexts=lambda: ([], {"name": "kind-cascade"}),
    load_kube_config=lambda: None,
)
sys.modules.setdefault("kubernetes", types.SimpleNamespace(client=fake_kubernetes_client, config=fake_kubernetes_config))
sys.modules.setdefault("kubernetes.client", fake_kubernetes_client)
sys.modules.setdefault("kubernetes.config", fake_kubernetes_config)


def load_module(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


command_center = load_module("security_command_center_api", "services/command-center-api/app/main.py")
approval_service = load_module("security_approval_service", "services/approval-service/app/main.py")
remediation_executor = load_module("security_remediation_executor", "services/remediation-executor-service/app/main.py")
chaos_executor = load_module("security_chaos_executor", "services/chaos-executor-service/app/main.py")
chaos_planner = load_module("security_chaos_planner", "services/chaos-planner-service/app/main.py")
autopilot_service = load_module("security_autopilot_service", "services/autopilot-service/app/main.py")
scheduler_service = load_module("security_scheduler_service", "services/scheduler-service/app/main.py")


def set_auth(module: Any, *, enabled: bool, bypass: bool = False, keys: str = "test-token") -> None:
    module.settings.cascade_auth_enabled = enabled
    module.settings.cascade_local_demo_auth_bypass = bypass
    module.settings.cascade_api_keys = keys
    module.settings.cascade_api_key_hashes = ""


def test_command_center_sensitive_write_requires_auth_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    set_auth(command_center, enabled=True)
    client = TestClient(command_center.app)
    response = client.post("/api/remediation/approval/approvals", json={"plan_id": "p"})
    assert response.status_code == 401
    set_auth(command_center, enabled=False)


def test_command_center_bad_token_rejected_when_enabled() -> None:
    set_auth(command_center, enabled=True)
    client = TestClient(command_center.app)
    response = client.post("/api/autopilot/runs", json={}, headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401
    set_auth(command_center, enabled=False)


def test_command_center_valid_token_reaches_existing_safety_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    set_auth(command_center, enabled=True)
    client = TestClient(command_center.app)
    response = client.post(
        "/api/remediation/executor/executions",
        json={"plan_id": "p", "approval_id": "a", "dry_run": False},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 403
    assert "Real remediation execution is disabled" in response.text
    set_auth(command_center, enabled=False)


def test_command_center_local_demo_auth_bypass_preserves_local_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    set_auth(command_center, enabled=True, bypass=True, keys="")

    async def fake_request(*args, **kwargs):
        class FakeResponse:
            status_code = 200
            content = b'{"status":"ok"}'
            headers = {"content-type": "application/json"}

        return FakeResponse()

    monkeypatch.setattr(command_center.httpx.AsyncClient, "request", fake_request)
    client = TestClient(command_center.app)
    response = client.post("/api/remediation/executor/executions/dry-run", json={"plan_id": "p"})
    assert response.status_code == 200
    set_auth(command_center, enabled=False, bypass=False)


@pytest.mark.parametrize(
    ("module", "path", "body"),
    [
        (approval_service, "/approvals", {"plan_id": "p", "decision": "approved", "approver": "me"}),
        (remediation_executor, "/executions", {"plan_id": "p", "approval_id": "a", "dry_run": False}),
        (chaos_executor, "/runs", {"plan_id": "p", "dry_run": False, "approved": True}),
        (chaos_planner, "/campaigns/camp-1/start", {"dry_run": True}),
        (autopilot_service, "/runs", {}),
        (scheduler_service, "/scheduler/items", {"item_type": "autopilot_run"}),
    ],
)
def test_direct_sensitive_services_require_auth_when_enabled(module: Any, path: str, body: dict[str, Any]) -> None:
    set_auth(module, enabled=True)
    response = TestClient(module.app).post(path, json=body)
    assert response.status_code == 401
    set_auth(module, enabled=False)


def test_approval_binding_accepts_exact_plan_and_rejects_changed_plan() -> None:
    plan = {
        "plan_id": "rem_plan_1",
        "action_type": "restart_deployment",
        "namespace": "cascade-targets",
        "service": "catalogue",
        "rollback_steps": ["roll back"],
    }
    metadata = approval_metadata(
        plan=plan,
        plan_type="remediation",
        actor="operator",
        risk_level="medium",
        policy_decision={"status": "requires_approval"},
        expires_minutes=30,
        signing_secret="secret",
    )
    approval = {
        "approval_id": "approval_1",
        "plan_id": "rem_plan_1",
        "decision": "approved",
        "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
        "metadata": metadata,
    }
    assert metadata["plan_hash"] == plan_hash(plan)
    assert approval_valid_for_plan(approval, plan, signing_secret="secret") == (True, [])
    changed = {**plan, "service": "front-end"}
    valid, reasons = approval_valid_for_plan(approval, changed, signing_secret="secret")
    assert valid is False
    assert "current plan contents" in "; ".join(reasons)


def test_audit_redaction_handles_bearer_jwt_url_credentials_and_kubeconfig_data() -> None:
    payload = {
        "headers": {"authorization": "Bearer abc.def.ghi"},
        "url": "https://user:password@example.test/path?token=abc123",
        "nested": {"client-key-data": "A" * 80, "id_token": "eyJabc.def.ghi"},
    }
    redacted = redact(payload)
    assert redacted["headers"]["authorization"] == REDACTED
    assert "password" not in redacted["url"]
    assert "token=abc123" not in redacted["url"]
    assert redacted["nested"]["client-key-data"] == REDACTED
    assert redacted["nested"]["id_token"] == REDACTED


def yaml_docs(path: str) -> list[dict[str, Any]]:
    with (ROOT / path).open("r", encoding="utf-8") as stream:
        return [doc for doc in yaml.safe_load_all(stream) if isinstance(doc, dict)]


def rules_for(path: str, kind: str) -> list[dict[str, Any]]:
    return [rule for doc in yaml_docs(path) if doc.get("kind") == kind for rule in doc.get("rules", [])]


def test_observation_and_topology_rbac_are_read_only() -> None:
    for path in ["infra/kubernetes/observation-service/rbac.yaml", "infra/kubernetes/topology-service/rbac.yaml"]:
        for rule in rules_for(path, "Role"):
            assert set(rule.get("verbs", [])) <= {"get", "list", "watch"}


def test_executor_rbac_has_no_wildcards_or_secret_mutation() -> None:
    forbidden_resources = {"secrets", "configmaps", "roles", "rolebindings", "clusterroles", "clusterrolebindings", "serviceaccounts", "namespaces"}
    for path in ["infra/kubernetes/chaos-executor-service/rbac.yaml", "infra/kubernetes/remediation-executor-service/rbac.yaml"]:
        for rule in rules_for(path, "Role") + rules_for(path, "ClusterRole"):
            resources = set(rule.get("resources", []))
            verbs = set(rule.get("verbs", []))
            assert "*" not in resources
            assert "*" not in verbs
            assert not (resources & forbidden_resources and verbs - {"get", "list", "watch"})
