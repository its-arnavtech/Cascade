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
