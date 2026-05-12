"""API Key authentication dependency."""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError


def _api_key_header(settings: Settings) -> APIKeyHeader:
    return APIKeyHeader(name=settings.api_key_header, auto_error=False)


async def require_api_key(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str | None:
    """Validate the API key header. If no keys are configured, auth is disabled."""
    allowed = settings.allowed_api_keys
    if not allowed:
        return None

    provided = (
        request.headers.get(settings.api_key_header)
        or request.query_params.get(settings.api_key_header)
    )
    if not provided or provided not in allowed:
        raise UnauthorizedError(
            "Missing or invalid API key",
            details={"header": settings.api_key_header},
        )
    return provided
    
