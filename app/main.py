"""FastAPI application entrypoint."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.v1 import router as v1_router
from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import register_rate_limiter
from app.schemas.download import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger(__name__)
    log.info(
        "app_startup",
        version=settings.app_version,
        environment=settings.environment,
        cache_backend=get_cache().backend,
        celery_eager=settings.use_eager_celery,
    )
    yield
    log.info("app_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Production-ready TikTok Video Downloader REST API.\n\n"
            "Watermark-free MP4/MP3 extraction via yt-dlp, async processing via "
            "Celery + Redis, per-IP rate limiting, API key auth, and structured "
            "JSON logging."
        ),
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
        openapi_url=settings.openapi_url,
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=[m.strip() for m in settings.cors_allow_methods.split(",")],
        allow_headers=[h.strip() for h in settings.cors_allow_headers.split(",")],
    )

    register_rate_limiter(app)
    register_exception_handlers(app)

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        log = get_logger("request")
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex)
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else None,
        )
        start = time.perf_counter()
        log.info("request_received")
        try:
            response = await call_next(request)
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("request_unhandled", error=str(exc))
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "Internal server error",
                        "status_code": 500,
                    }
                },
            )
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        log.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        structlog.contextvars.clear_contextvars()
        return response

    # Routers
    app.include_router(v1_router)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        s = get_settings()
        return HealthResponse(
            status="ok",
            version=__version__,
            environment=s.environment,
            cache=get_cache().ping(),
            celery_eager=s.use_eager_celery,
        )

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        s = get_settings()
        return {
            "name": s.app_name,
            "version": s.app_version,
            "docs": s.docs_url,
            "redoc": s.redoc_url,
            "health": "/health",
        }

    return app


app = create_app()
