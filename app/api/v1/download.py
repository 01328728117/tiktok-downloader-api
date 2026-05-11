"""POST /api/v1/download endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import cache_dep
from app.core.cache import CacheBackend
from app.core.rate_limit import limiter
from app.core.security import require_api_key
from app.schemas.download import DownloadRequest, DownloadResponse, TaskStatus
from app.workers.celery_app import queue_download

router = APIRouter(tags=["download"])


@router.post(
    "/download",
    response_model=DownloadResponse,
    status_code=202,
    summary="Queue a TikTok video download",
    dependencies=[Depends(require_api_key)],
)
@limiter.limit("60/minute")
async def create_download(
    request: Request,
    payload: DownloadRequest,
    cache: CacheBackend = Depends(cache_dep),
) -> DownloadResponse:
    """Queue an async TikTok extraction task and return its task_id."""
    task_id, cached = queue_download(payload.url, payload.quality, payload.format)
    task = cache.get_task(task_id)
    status_value = TaskStatus(task["status"]) if task else TaskStatus.queued

    base = str(request.base_url).rstrip("/")
    return DownloadResponse(
        task_id=task_id,
        status=status_value,
        cached=cached,
        poll_url=f"{base}/api/v1/status/{task_id}",
        result_url=f"{base}/api/v1/result/{task_id}",
    )
