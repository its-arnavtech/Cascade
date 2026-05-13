from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class QdrantSettings(BaseSettings):
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "cascade_incident_memory"
    embedding_dimensions: int = 128
    qdrant_timeout_seconds: float = 10.0

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


class QdrantClient:
    def __init__(self, settings: QdrantSettings | None = None) -> None:
        self.settings = settings or QdrantSettings()

    async def ping(self) -> bool:
        try:
            async with self._client() as client:
                response = await client.get("/readyz")
                return response.status_code < 500
        except Exception as exc:
            logger.warning("Qdrant ping failed: %s", exc)
            return False

    async def ensure_collection(self) -> None:
        if await self.collection_ready():
            return
        payload = {
            "vectors": {
                "size": self.settings.embedding_dimensions,
                "distance": "Cosine",
            }
        }
        await self._with_retry(lambda: self._put(f"/collections/{self.settings.qdrant_collection}", payload, conflict_ok=True))

    async def upsert_point(self, memory_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        point_id = self.point_id(memory_id)
        body = {"points": [{"id": point_id, "vector": vector, "payload": payload}]}
        await self._with_retry(lambda: self._put(f"/collections/{self.settings.qdrant_collection}/points?wait=true", body))
        logger.info("Upserted Qdrant memory memory_id=%s point_id=%s", memory_id, point_id)

    async def search(self, vector: list[float], limit: int = 5, service: str | None = None, namespace: str | None = None, memory_type: str | None = None) -> list[dict[str, Any]]:
        filters = []
        for key, value in {"service": service, "namespace": namespace, "memory_type": memory_type}.items():
            if value:
                filters.append({"key": key, "match": {"value": value}})
        body: dict[str, Any] = {
            "vector": vector,
            "limit": max(1, min(int(limit), 50)),
            "with_payload": True,
        }
        if filters:
            body["filter"] = {"must": filters}
        async with self._client() as client:
            response = await client.post(f"/collections/{self.settings.qdrant_collection}/points/search", json=body)
            response.raise_for_status()
            return response.json().get("result", [])

    async def count(self) -> int:
        async with self._client() as client:
            response = await client.post(f"/collections/{self.settings.qdrant_collection}/points/count", json={"exact": True})
            response.raise_for_status()
            return int(response.json().get("result", {}).get("count", 0))

    async def collection_ready(self) -> bool:
        try:
            async with self._client() as client:
                response = await client.get(f"/collections/{self.settings.qdrant_collection}")
                return response.status_code == 200
        except Exception:
            return False

    @staticmethod
    def point_id(memory_id: str) -> str:
        digest = hashlib.md5(memory_id.encode("utf-8"), usedforsecurity=False).hexdigest()
        return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:]}"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.settings.qdrant_url.rstrip("/"), timeout=self.settings.qdrant_timeout_seconds)

    async def _put(self, path: str, body: dict[str, Any], conflict_ok: bool = False) -> None:
        async with self._client() as client:
            response = await client.put(path, json=body)
            if conflict_ok and response.status_code == 409:
                return
            response.raise_for_status()

    async def _with_retry(self, action, attempts: int = 5) -> None:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                await action()
                return
            except Exception as exc:
                last_error = exc
                logger.warning("Qdrant operation failed attempt=%s/%s error=%s", attempt, attempts, exc)
                await asyncio.sleep(attempt)
        raise RuntimeError("Qdrant operation failed") from last_error
