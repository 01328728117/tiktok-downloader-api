"""Application-specific exceptions and structured JSON error handlers."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


class APIError(Exception):
    """Base class for API errors that map to structured JSON responses."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.details = details or {}


class InvalidTikTokURLError(APIError):
    status_code = 400
    code = "invalid_url"


class VideoUnavailableError(APIError):
    status_code = 404
    code = "video_unavailable"


class VideoPrivateError(APIError):
    status_code = 403
    code = "video_private"


class ExtractionError(APIError):
    status_code = 502
    code = "extraction_failed"


class TaskNotFoundError(APIError):
    status_code = 404
    code = "task_not_found"


class TaskNotReadyError(APIError):
    status_code = 425  # Too Early
    code = "task_not_ready"


class UnauthorizedError(APIError):
    status_code = 401
    code = "unauthorized"


def _error_payload(
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "status_code": status_code,
        }
    }
    if details:
        payload["error"]["details"] = details
    return payload


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    logger.warning(
        "api_error",
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(exc.code, exc.message, exc.status_code, exc.details),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "http_error"
    if exc.status_code == 404:
        code = "not_found"
    elif exc.status_code == 401:
        code = "unauthorized"
    elif exc.status_code == 403:
        code = "forbidden"
    elif exc.status_code == 429:
        code = "rate_limited"
    message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(code, message, exc.status_code),
    )


def _jsonable_errors(errors):
    """Strip non-JSON-serializable fields from Pydantic v2 validation errors.

    Pydantic v2 includes the original Python exception under the ``ctx`` key,
    which is not JSON-serializable. Stringify any non-primitive values.
    """
    cleaned: list[dict[str, Any]] = []
    for err in errors:
        if not isinstance(err, dict):
            cleaned.append({"detail": str(err)})
            continue
        item: dict[str, Any] = {}
        for key, value in err.items():
            if key == "ctx" and isinstance(value, dict):
                item["ctx"] = {k: str(v) for k, v in value.items()}
            elif isinstance(value, tuple):
                item[key] = [str(v) for v in value]
            elif isinstance(value, (str, int, float, bool, list, dict, type(None))):
                item[key] = value
            else:
                item[key] = str(value)
        cleaned.append(item)
    return cleaned


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            "validation_error",
            "Request validation failed",
            422,
            {"errors": _jsonable_errors(exc.errors())},
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content=_error_payload("internal_error", "Internal server error", 500),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
