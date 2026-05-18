from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("command-center-api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


class Settings(BaseSettings):
    retrieval_service_url: str = "http://retrieval-service.cascade-system.svc.cluster.local:8012"
    knowledge_retrieval_service_url: str = "http://knowledge-retrieval-service.cascade-system.svc.cluster.local:8016"
    topology_service_url: str = "http://topology-service.cascade-system.svc.cluster.local:8004"
    causal_reconstruction_service_url: str = "http://causal-reconstruction-service.cascade-system.svc.cluster.local:8005"
    incident_timeline_service_url: str = "http://incident-timeline-service.cascade-system.svc.cluster.local:8006"
    agent_tool_gateway_url: str = "http://agent-tool-gateway.cascade-system.svc.cluster.local:8017"
    agent_orchestrator_service_url: str = "http://agent-orchestrator-service.cascade-system.svc.cluster.local:8018"
    chaos_planner_service_url: str = "http://chaos-planner-service.cascade-system.svc.cluster.local:8019"
    chaos_executor_service_url: str = "http://chaos-executor-service.cascade-system.svc.cluster.local:8020"
    remediation_recommender_service_url: str = "http://remediation-recommender-service.cascade-system.svc.cluster.local:8021"
    approval_service_url: str = "http://approval-service.cascade-system.svc.cluster.local:8022"
    remediation_executor_service_url: str = "http://remediation-executor-service.cascade-system.svc.cluster.local:8023"
    anomaly_detector_service_url: str = "http://anomaly-detector-service.cascade-system.svc.cluster.local:8014"
    feature_extractor_service_url: str = "http://feature-extractor-service.cascade-system.svc.cluster.local:8013"
    proxy_timeout_seconds: float = 10.0
    enable_dangerous_actions: bool = False
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 120
    rate_limit_burst: int = 60

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


settings = Settings()
app = FastAPI(title="Cascade Command Center API", version="0.1.0")


@dataclass
class InMemoryRateLimiter:
    requests_per_minute: int
    burst: int
    buckets: dict[str, list[float]] = field(default_factory=dict)

    def allow(self, key: str, now: float | None = None) -> tuple[bool, int]:
        current = time.monotonic() if now is None else now
        cutoff = current - 60.0
        bucket = [ts for ts in self.buckets.get(key, []) if ts > cutoff]
        limit = max(1, self.requests_per_minute + max(0, self.burst))
        remaining = max(0, limit - len(bucket))
        if len(bucket) >= limit:
            self.buckets[key] = bucket
            return False, 0
        bucket.append(current)
        self.buckets[key] = bucket
        return True, max(0, remaining - 1)

    def reset(self) -> None:
        self.buckets.clear()


rate_limiter = InMemoryRateLimiter(
    requests_per_minute=settings.rate_limit_requests_per_minute,
    burst=settings.rate_limit_burst,
)

ROUTES: dict[str, str] = {
    "retrieval": settings.retrieval_service_url,
    "knowledge": settings.knowledge_retrieval_service_url,
    "topology": settings.topology_service_url,
    "causality": settings.retrieval_service_url,
    "causal-reconstruction": settings.causal_reconstruction_service_url,
    "target": settings.topology_service_url,
    "timeline": settings.incident_timeline_service_url,
    "agent": settings.agent_orchestrator_service_url,
    "tools": settings.agent_tool_gateway_url,
    "chaos/planner": settings.chaos_planner_service_url,
    "chaos/executor": settings.chaos_executor_service_url,
    "remediation/recommender": settings.remediation_recommender_service_url,
    "remediation/approval": settings.approval_service_url,
    "remediation/executor": settings.remediation_executor_service_url,
    "anomaly": settings.anomaly_detector_service_url,
    "features": settings.feature_extractor_service_url,
}

ALLOWED_METHODS = {"GET", "POST"}
SAFE_POST_PATHS = {
    ("knowledge", "knowledge/search"),
    ("knowledge", "knowledge/context"),
    ("topology", "topology/impact"),
    ("topology", "topology/blast-radius"),
    ("topology", "topology/critical-paths"),
    ("causality", "causality/analyze"),
    ("causal-reconstruction", "reconstruct"),
    ("timeline", "timeline"),
    ("timeline", "report"),
    ("agent", "investigations"),
    ("chaos/planner", "plans"),
    ("chaos/executor", "runs"),
    ("remediation/recommender", "plans"),
    ("remediation/approval", "approvals"),
    ("remediation/executor", "executions/dry-run"),
}


@app.middleware("http")
async def apply_rate_limit(request: Request, call_next):
    if not settings.rate_limit_enabled or request.url.path in {"/health", "/ready"}:
        return await call_next(request)

    rate_limiter.requests_per_minute = settings.rate_limit_requests_per_minute
    rate_limiter.burst = settings.rate_limit_burst
    allowed, remaining = rate_limiter.allow(_client_key(request))
    if not allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": "Command Center API rate limit exceeded",
                "retry_after_seconds": 60,
                "limit": settings.rate_limit_requests_per_minute,
                "burst": settings.rate_limit_burst,
            },
            headers={"Retry-After": "60", "X-RateLimit-Remaining": "0"},
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "command-center-api", "dangerous_actions_enabled": settings.enable_dangerous_actions}


@app.get("/ready")
async def ready() -> dict[str, Any]:
    checks = {}
    async with httpx.AsyncClient(timeout=settings.proxy_timeout_seconds) as client:
        for route, base_url in ROUTES.items():
            checks[route] = await _check(client, base_url)
    return {"status": "ok" if any(checks.values()) else "degraded", "service": "command-center-api", "checks": checks}


@app.api_route("/api/{route:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(route: str, request: Request) -> Response:
    if request.method not in ALLOWED_METHODS:
        raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED, detail="Command Center API allows only GET and POST")

    prefix, upstream_path = _resolve_route(route)
    body = await request.body()
    _enforce_safety(prefix, upstream_path, request.method, body)
    target = f"{ROUTES[prefix].rstrip('/')}/{upstream_path}".rstrip("/")
    headers = _forward_headers(request.headers)

    try:
        async with httpx.AsyncClient(timeout=settings.proxy_timeout_seconds) as client:
            upstream = await client.request(
                request.method,
                target,
                params=request.query_params,
                content=body if body else None,
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail=f"Upstream timeout for {prefix}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream unavailable for {prefix}: {exc.__class__.__name__}") from exc

    response_headers = {"x-cascade-upstream": prefix}
    content_type = upstream.headers.get("content-type")
    if content_type:
        response_headers["content-type"] = content_type
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)


def _resolve_route(route: str) -> tuple[str, str]:
    cleaned = route.strip("/")
    for prefix in sorted(ROUTES, key=len, reverse=True):
        if cleaned == prefix:
            return prefix, ""
        marker = prefix + "/"
        if cleaned.startswith(marker):
            return prefix, cleaned[len(marker) :]
    raise HTTPException(status_code=404, detail="Unknown Command Center API route")


def _enforce_safety(prefix: str, upstream_path: str, method: str, body: bytes) -> None:
    if method != "POST":
        return
    normalized = upstream_path.strip("/")
    if (prefix, normalized) not in SAFE_POST_PATHS and not _is_safe_analysis_post(prefix, normalized):
        raise HTTPException(status_code=403, detail="This Command Center POST route is not exposed")

    if settings.enable_dangerous_actions:
        return
    payload = _json_body(body)
    if prefix == "remediation/executor" and normalized != "executions/dry-run":
        raise HTTPException(status_code=403, detail="Real remediation execution is disabled by default")
    if prefix == "chaos/planner" and normalized == "plans" and payload.get("dry_run") is not True:
        raise HTTPException(status_code=403, detail="Only dry-run chaos plans are exposed by default")
    if prefix == "chaos/executor" and normalized == "runs":
        if payload.get("dry_run") is not True or payload.get("approved") is True:
            raise HTTPException(status_code=403, detail="Only chaos dry-run execution is exposed by default")


def _is_safe_analysis_post(prefix: str, normalized_path: str) -> bool:
    if prefix in {"chaos/planner", "remediation/recommender"}:
        parts = normalized_path.strip("/").split("/")
        return len(parts) == 3 and parts[0] == "plans" and parts[2] == "validate"
    return False


def _json_body(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        import json

        parsed = json.loads(body.decode("utf-8"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _forward_headers(headers: Mapping[str, str]) -> dict[str, str]:
    allowed = {}
    for key in ("content-type", "accept"):
        if key in headers:
            allowed[key] = headers[key]
    return allowed


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


async def _check(client: httpx.AsyncClient, base_url: str) -> bool:
    try:
        response = await client.get(base_url.rstrip("/") + "/health")
        return response.status_code < 500
    except Exception:
        return False
