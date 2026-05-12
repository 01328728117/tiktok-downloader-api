"""GET /api/v1/proxy/{task_id} — stream video/audio through the server."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.api.deps import cache_dep
from app.core.cache import CacheBackend
from app.core.config import get_settings
from app.core.exceptions import (
    APIError,
    ExtractionError,
    TaskNotFoundError,
    TaskNotReadyError,
)
from app.core.rate_limit import limiter
from app.core.security import require_api_key
from app.schemas.download import DownloadResult, TaskStatus

router = APIRouter(tags=["proxy"])

_settings = get_settings()


@router.get(
    "/proxy/{task_id}",
    summary="Proxy-download the video or audio for a completed task",
    dependencies=[Depends(require_api_key)],
)
@limiter.limit("30/minute")
async def proxy_download(
    request: Request,
    task_id: str,
    type: str = Query("video", pattern="^(video|audio)$"),
    cache: CacheBackend = Depends(cache_dep),
) -> StreamingResponse:
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

    result = DownloadResult.model_validate(result_payload)

    if type == "audio":
        url = str(result.audio_url) if result.audio_url else None
        filename = f"tiktok_audio_{task_id[:8]}.m4a"
        content_type = "audio/mp4"
    else:
        url = str(result.download_url) if result.download_url else None
        filename = f"tiktok_video_{task_id[:8]}.mp4"
        content_type = "video/mp4"

    if not url:
        raise ExtractionError(f"No {type} URL available for this task")

    headers = {
        "User-Agent": _settings.ytdlp_user_agent,
        "Referer": "https://www.tiktok.com/",
        "Accept": "*/*",
    }

    client = httpx.AsyncClient(timeout=60, follow_redirects=True)
    upstream = await client.send(
        client.build_request("GET", url, headers=headers),
        stream=True,
    )

    if upstream.status_code >= 400:
        await upstream.aclose()
        await client.aclose()
        raise ExtractionError(
            f"TikTok CDN returned {upstream.status_code}. "
            "Link may have expired \u2014 try downloading again."
        )

    async def stream_and_close():
        try:
            async for chunk in upstream.aiter_bytes(chunk_size=65536):
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    resp_headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    cl = upstream.headers.get("content-length")
    if cl:
        resp_headers["Content-Length"] = cl

    return StreamingResponse(
        stream_and_close(),
        status_code=200,
        media_type=content_type,
        headers=resp_headers,
  )
  
