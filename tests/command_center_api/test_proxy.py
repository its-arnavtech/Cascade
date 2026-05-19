from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


MODULE_PATH = Path(__file__).resolve().parents[2] / "services" / "command-center-api" / "app" / "main.py"
spec = importlib.util.spec_from_file_location("command_center_api_main", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["command_center_api_main"] = module
spec.loader.exec_module(module)


client = TestClient(module.app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "command-center-api"


def test_unknown_proxy_target_rejected() -> None:
    response = client.get("/api/not-a-service/health")
    assert response.status_code == 404


def test_method_allowlist() -> None:
    response = client.delete("/api/retrieval/health")
    assert response.status_code == 405


def test_real_remediation_execution_blocked_by_default() -> None:
    response = client.post("/api/remediation/executor/executions", json={"plan_id": "p", "approval_id": "a"})
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("url", "body"),
    [
        ("/api/remediation/executor/executions/dry-run", {}),
        ("/api/chaos/planner/plans", {"dry_run": True}),
        ("/api/chaos/executor/runs", {"dry_run": True, "approved": False}),
        ("/api/agent/investigations", {}),
        ("/api/topology/topology/impact", {"root_service": "catalogue"}),
        ("/api/topology/topology/blast-radius", {"root_service": "catalogue"}),
        ("/api/topology/topology/critical-paths", {"root_service": "catalogue"}),
        ("/api/causality/causality/analyze", {"target_service": "catalogue"}),
        ("/api/causal-reconstruction/reconstruct", {"experiment_id": "exp-1"}),
        ("/api/timeline/timeline", {}),
        ("/api/timeline/report", {}),
        ("/api/chaos/planner/plans/plan-1/validate", {}),
        ("/api/remediation/recommender/plans/plan-1/validate", {}),
    ],
)
def test_safe_create_routes_not_blocked_by_safety_gate(monkeypatch: pytest.MonkeyPatch, url: str, body: dict[str, object]) -> None:
    async def fake_request(*args, **kwargs):
        class FakeResponse:
            status_code = 200
            content = b'{"status":"ok"}'
            headers = {"content-type": "application/json"}

        return FakeResponse()

    monkeypatch.setattr(module.httpx.AsyncClient, "request", fake_request)
    response = client.post(url, json=body)
    assert response.status_code == 200


def test_real_chaos_run_blocked_by_default() -> None:
    response = client.post("/api/chaos/executor/runs", json={"dry_run": False, "approved": True})
    assert response.status_code == 403


def test_topology_graph_alias_proxies_existing_service_route(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    async def fake_get(self, url, **kwargs):
        seen["url"] = url

        class FakeResponse:
            status_code = 200
            content = b'{"nodes":[],"edges":[]}'
            headers = {"content-type": "application/json"}

            def json(self):
                return {"nodes": [], "edges": [], "source": "target-catalog"}

        return FakeResponse()

    monkeypatch.setattr(module.httpx.AsyncClient, "get", fake_get)
    response = client.get("/api/topology/graph")
    assert response.status_code == 200
    assert response.json()["source"] == "target-catalog"
    assert seen["url"].endswith("/topology/graph")


def test_topology_graph_alias_falls_back_to_topology_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    async def fake_get(self, url, **kwargs):
        calls.append(url)

        class FakeResponse:
            headers = {"content-type": "application/json"}

            def __init__(self, status_code, payload):
                self.status_code = status_code
                self._payload = payload
                self.content = b"{}"

            def json(self):
                return self._payload

        if url.endswith("/topology/graph"):
            return FakeResponse(404, {"detail": "Not Found"})
        return FakeResponse(200, {"dependencies": {"front-end": ["catalogue"], "catalogue": []}})

    monkeypatch.setattr(module.httpx.AsyncClient, "get", fake_get)
    response = client.get("/api/topology/graph")
    assert response.status_code == 200
    assert response.json()["dependencies"]["front-end"] == ["catalogue"]
    assert response.json()["source"] == "topology-service-fallback"
    assert calls[-1].endswith("/topology")


def test_live_demo_status_reports_policy_without_enforcing_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self, url, **kwargs):
        class FakeResponse:
            status_code = 200

            def __init__(self, payload):
                self._payload = payload

            def json(self):
                return self._payload

        if url.endswith("/target/workload"):
            return FakeResponse({"safe_chaos_services": ["catalogue"], "protected_services": ["front-end"]})
        if "chaos-executor" in url:
            return FakeResponse({"live_demo_mode": True, "dangerous_actions_enabled": True, "real_chaos_enabled": True, "allowed_target_namespace": "cascade-targets", "allowed_services": ["catalogue"], "protected": {"services": ["front-end"]}, "supported_kinds": ["pod_kill"]})
        return FakeResponse({"live_demo_mode": True, "dangerous_actions_enabled": True, "real_remediation_enabled": True, "execution_enabled": True, "allowed_target_namespace": "cascade-targets", "allowed_services": ["catalogue"], "protected": {"services": ["front-end"]}, "supported_action_types": ["restart_deployment"]})

    monkeypatch.setattr(module.httpx.AsyncClient, "get", fake_get)
    response = client.get("/api/live-demo/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["chaos"]["allowed_actions"] == ["pod_kill"]
    assert payload["remediation"]["allowed_actions"] == ["restart_deployment"]
    assert payload["command_center"]["dangerous_actions_enabled"] is False
    assert "Command Center proxy gate ENABLE_DANGEROUS_ACTIONS is false" in payload["chaos"]["disabled_reasons"]
    assert "Command Center proxy gate ENABLE_DANGEROUS_ACTIONS is false" in payload["remediation"]["disabled_reasons"]


def test_live_demo_status_explains_disabled_executor_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self, url, **kwargs):
        class FakeResponse:
            status_code = 200

            def __init__(self, payload):
                self._payload = payload

            def json(self):
                return self._payload

        if url.endswith("/target/workload"):
            return FakeResponse({"safe_chaos_services": ["catalogue"], "protected_services": []})
        return FakeResponse({"allowed_target_namespace": "default", "allowed_services": ["catalogue"], "supported_kinds": [], "supported_action_types": []})

    monkeypatch.setattr(module.httpx.AsyncClient, "get", fake_get)
    response = client.get("/api/live-demo/status")
    assert response.status_code == 200
    payload = response.json()
    assert "CASCADE_LIVE_DEMO_MODE is false" in payload["chaos"]["disabled_reasons"]
    assert "Allowed target namespace is not cascade-targets" in payload["remediation"]["disabled_reasons"]


@pytest.mark.parametrize(
    ("url", "body"),
    [
        ("/api/chaos/executor/runs", {"plan_id": "p", "dry_run": False, "approved": True, "approval_id": "a"}),
        ("/api/remediation/executor/executions", {"plan_id": "p", "dry_run": False, "approval_id": "a"}),
    ],
)
def test_real_execution_routes_forward_only_when_proxy_dangerous_flag_enabled(monkeypatch: pytest.MonkeyPatch, url: str, body: dict[str, object]) -> None:
    monkeypatch.setattr(module.settings, "enable_dangerous_actions", True)

    async def fake_request(*args, **kwargs):
        class FakeResponse:
            status_code = 400
            content = b'{"detail":{"status":"rejected","violations":["backend safety still enforced"]}}'
            headers = {"content-type": "application/json"}

        return FakeResponse()

    monkeypatch.setattr(module.httpx.AsyncClient, "request", fake_request)
    response = client.post(url, json=body)
    assert response.status_code == 400
    assert "backend safety still enforced" in response.text
    monkeypatch.setattr(module.settings, "enable_dangerous_actions", False)


@pytest.mark.parametrize(
    "url",
    [
        "/api/chaos/executor/runs/chaos_run_1/cleanup",
        "/api/chaos/executor/runs/chaos_run_1/observe",
        "/api/remediation/recommender/plans/from-latest-anomaly",
        "/api/remediation/executor/executions/rem_exec_1/retry",
    ],
)
def test_dangerous_or_unreviewed_post_routes_blocked_by_default(url: str) -> None:
    response = client.post(url, json={})
    assert response.status_code == 403


def test_rate_limiter_blocks_after_configured_window(monkeypatch: pytest.MonkeyPatch) -> None:
    module.rate_limiter.reset()
    monkeypatch.setattr(module.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(module.settings, "rate_limit_requests_per_minute", 1)
    monkeypatch.setattr(module.settings, "rate_limit_burst", 0)

    first = client.get("/api/not-a-service/health", headers={"X-Forwarded-For": "198.51.100.10"})
    second = client.get("/api/not-a-service/health", headers={"X-Forwarded-For": "198.51.100.10"})

    assert first.status_code == 404
    assert second.status_code == 429
    assert second.json()["detail"] == "Command Center API rate limit exceeded"
    module.rate_limiter.reset()


def test_rate_limiter_exempts_health_and_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    module.rate_limiter.reset()
    monkeypatch.setattr(module.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(module.settings, "rate_limit_requests_per_minute", 1)
    monkeypatch.setattr(module.settings, "rate_limit_burst", 0)

    for _ in range(3):
        assert client.get("/health").status_code == 200

    module.rate_limiter.reset()
