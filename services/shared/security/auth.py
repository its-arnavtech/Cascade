from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class AuthSettings:
    enabled: bool = False
    local_demo_bypass: bool = False
    api_keys: str = ""
    api_key_hashes: str = ""
    auth_header: str = "Authorization"


def auth_status(settings: AuthSettings) -> dict[str, Any]:
    return {
        "auth_enabled": settings.enabled,
        "local_demo_auth_bypass": settings.local_demo_bypass,
        "auth_header": settings.auth_header,
        "configured_keys": len(_split(settings.api_keys)) + len(_split(settings.api_key_hashes)),
    }


def require_auth(request: Request, settings: AuthSettings, *, action: str = "sensitive action") -> dict[str, str]:
    if not settings.enabled:
        return {"actor": "local-unauthenticated", "auth_mode": "disabled"}
    if settings.local_demo_bypass:
        return {"actor": "local-demo-bypass", "auth_mode": "local_demo_bypass"}

    configured_plain = _split(settings.api_keys)
    configured_hashes = _split(settings.api_key_hashes)
    if not configured_plain and not configured_hashes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Auth is enabled but no API keys are configured for {action}",
        )

    token = _extract_token(request, settings.auth_header)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication required for {action}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if _token_matches(token, configured_plain, configured_hashes):
        return {"actor": _actor(request), "auth_mode": "api_key"}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid Cascade API token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_token(request: Request, header_name: str) -> str:
    value = request.headers.get(header_name) or request.headers.get("X-Cascade-Api-Key") or ""
    if header_name.lower() != "authorization" and value:
        return value.strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value.strip()


def _token_matches(token: str, plain_keys: list[str], key_hashes: list[str]) -> bool:
    for key in plain_keys:
        if hmac.compare_digest(token, key):
            return True
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return any(hmac.compare_digest(digest, key_hash.lower()) for key_hash in key_hashes)


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _actor(request: Request) -> str:
    explicit = request.headers.get("X-Cascade-Actor", "").strip()
    if explicit:
        return explicit[:128]
    return "authenticated-operator"

