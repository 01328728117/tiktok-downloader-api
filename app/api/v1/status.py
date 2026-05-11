"""GET /api/v1/status/{task_id} endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import cache_dep
from app.core.cache import CacheBackend
from app.core.exceptions import TaskNotFoundError
from app.core.rate_limit import limiter
from app.core.security import require_api_key
from app.schemas.download import StatusResponse, TaskStatus

router = APIRouter(tags=["status"])


@router.get(
    "/status/{task_id}",
    response_model=StatusResponse,
    summary="Get task processing status",
    dependencies=[Depends(require_api_key)],
)
@limiter.limit("60/minute")
async def get_status(
    request: Request,
    task_id: str,
    cache: CacheBackend = Depends(cache_dep),
) -> StatusResponse:
    task = cache.get_task(task_id)
    if not task:
        raise TaskNotFoundError(f"Task {task_id} not found")

    status = TaskStatus(task.get("status", TaskStatus.queued.value))
    base = str(request.base_url).rstrip("/")
    result_url = f"{base}/api/v1/result/{task_id}" if status == TaskStatus.completed else None
    return StatusResponse(
        task_id=task_id,
        status=status,
        progress=int(task.get("progress", 0)),
        message=task.get("message"),
        error=task.get("error"),
        updated_at=float(task.get("updated_at", 0.0)),
        result_url=result_url,
    )
