import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class PrometheusError(RuntimeError):
    """Raised when Prometheus returns an error or cannot be reached."""


class PrometheusClient:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds)

    async def query(self, promql: str) -> dict[str, Any]:
        """Run an instant Prometheus query and return the decoded API response."""
        url = f"{self._base_url}/api/v1/query"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
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
