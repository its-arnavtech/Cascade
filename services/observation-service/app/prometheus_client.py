import logging
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PrometheusError(RuntimeError):
    """Raised when Prometheus returns an error or cannot be reached."""


class PrometheusQueryStatus(BaseModel):
    metric: str
    query: str
    status: str
    result_count: int = 0
    warning: str | None = None
    error: str | None = None


class PrometheusQueryResult(BaseModel):
    metric: str
    query: str
    payload: dict[str, Any] | None = None
    status: PrometheusQueryStatus


class PrometheusClient:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds)
        self._transport = transport

    async def query(self, promql: str) -> dict[str, Any]:
        """Run an instant Prometheus query and return the decoded API response."""
        url = f"{self._base_url}/api/v1/query"
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.get(url, params={"query": promql})
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("Prometheus query failed with HTTP status %s", exc.response.status_code)
            raise PrometheusError(f"Prometheus returned HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            logger.warning("Prometheus request failed: %s", exc)
            raise PrometheusError("Unable to reach Prometheus") from exc
        except ValueError as exc:
            logger.warning("Prometheus returned invalid JSON")
            raise PrometheusError("Prometheus returned invalid JSON") from exc

        if payload.get("status") != "success":
            error_type = payload.get("errorType", "unknown")
            error = payload.get("error", "Prometheus query failed")
            logger.warning("Prometheus query error: %s: %s", error_type, error)
            raise PrometheusError(f"Prometheus query error ({error_type}): {error}")

        return payload

    async def query_with_status(self, metric: str, promql: str) -> PrometheusQueryResult:
        """Run a query and preserve failure/empty states without fabricating values."""
        try:
            payload = await self.query(promql)
        except PrometheusError as exc:
            return PrometheusQueryResult(
                metric=metric,
                query=promql,
                payload=None,
                status=PrometheusQueryStatus(metric=metric, query=promql, status="failed", error=str(exc)),
            )

        result_count = _result_count(payload)
        status = "success" if result_count else "empty"
        warning = None if result_count else "Prometheus query succeeded but returned no samples."
        return PrometheusQueryResult(
            metric=metric,
            query=promql,
            payload=payload,
            status=PrometheusQueryStatus(metric=metric, query=promql, status=status, result_count=result_count, warning=warning),
        )


def _result_count(payload: dict[str, Any]) -> int:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    result = data.get("result")
    return len(result) if isinstance(result, list) else 0
