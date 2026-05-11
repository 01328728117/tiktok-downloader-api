"""SlowAPI-based per-IP rate limiting."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.config import get_settings

_settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_settings.rate_limit] if _settings.rate_limit_enabled else [],
    enabled=_settings.rate_limit_enabled,
    storage_uri=_settings.redis_url or "memory://",
    strategy="fixed-window",
)


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    detail = getattr(exc, "detail", "Rate limit exceeded")
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limited",
                "message": f"Rate limit exceeded: {detail}",
                "status_code": 429,
            }
        },
    )


def register_rate_limiter(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
