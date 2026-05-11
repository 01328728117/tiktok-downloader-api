"""GET /api/v1/result/{task_id} endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import cache_dep
from app.core.cache import CacheBackend
from app.core.exceptions import (
    APIError,
    ExtractionError,
    TaskNotFoundError,
    TaskNotReadyError,
)
from app.core.rate_limit import limiter
from app.core.security import require_api_key
from app.schemas.download import DownloadResult, TaskStatus

router = APIRouter(tags=["result"])


@router.get(
    "/result/{task_id}",
    response_model=DownloadResult,
    summary="Get watermark-free download URL for a completed task",
    dependencies=[Depends(require_api_key)],
)
@limiter.limit("60/minute")
async def get_result(
    request: Request,
    task_id: str,
    cache: CacheBackend = Depends(cache_dep),
) -> DownloadResult:
    task = cache.get_task(task_id)
    if not task:
        raise TaskNotFoundError(f"Task {task_id} not found")

    status = TaskStatus(task.get("status", TaskStatus.queued.value))
    if status == TaskStatus.failed:
        err = task.get("error") or {}
        raise APIError(
            err.get("message", "Task failed"),
            status_code=err.get("status_code", 502),
            code=err.get("code", "extraction_failed"),
        )
    if status != TaskStatus.completed:
        raise TaskNotReadyError(f"Task {task_id} is not ready (status={status.value})")

    result_payload = task.get("result")
    if not result_payload:
        raise ExtractionError("Result payload missing from completed task")

    return DownloadResult.model_validate(result_payload)
