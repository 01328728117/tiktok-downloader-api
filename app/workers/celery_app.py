"""Celery application + tasks for async TikTok video processing."""

from __future__ import annotations

import time
import uuid
from typing import Any

from celery import Celery, Task

from app.core.cache import CacheBackend, get_cache
from app.core.config import get_settings
from app.core.exceptions import APIError
from app.core.logging import configure_logging, get_logger
from app.schemas.download import OutputFormat, Quality, TaskStatus
from app.services.tiktok import TikTokService

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


def _build_celery() -> Celery:
    broker = settings.celery_broker_url or "memory://"
    backend = settings.celery_result_backend or "cache+memory://"
    app = Celery(
        "tiktok_downloader",
        broker=broker,
        backend=backend,
        include=["app.workers.celery_app"],
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=settings.celery_task_time_limit,
        task_soft_time_limit=settings.celery_task_soft_time_limit,
        broker_connection_retry_on_startup=True,
        task_always_eager=settings.use_eager_celery,
        task_eager_propagates=False,
        worker_send_task_events=True,
        task_send_sent_event=True,
    )
    return app


celery_app = _build_celery()


def new_task_id() -> str:
    return uuid.uuid4().hex


def _now() -> float:
    return time.time()


def _update_task(
    cache: CacheBackend,
    task_id: str,
    *,
    status: TaskStatus,
    progress: int = 0,
    message: str | None = None,
    error: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    payload = cache.get_task(task_id) or {"task_id": task_id}
    payload.update(
        {
            "task_id": task_id,
            "status": status.value,
            "progress": progress,
            "message": message,
            "error": error,
            "updated_at": _now(),
        }
    )
    if result is not None:
        payload["result"] = result
    cache.set_task(task_id, payload, ttl=settings.cache_ttl_seconds)


def queue_download(url: str, quality: Quality, output_format: OutputFormat) -> tuple[str, bool]:
    """Queue a download task.

    Returns ``(task_id, cached)`` — if the URL has already been processed
    successfully within the cache window, the existing task_id is returned and
    cached=True.
    """
    cache = get_cache()
    cache_key = f"url:{url}:{quality.value}:{output_format.value}"
    existing_id = cache.get_json(cache_key)
    if isinstance(existing_id, str):
        existing = cache.get_task(existing_id)
        if existing and existing.get("status") == TaskStatus.completed.value:
            return existing_id, True

    task_id = new_task_id()
    _update_task(
        cache,
        task_id,
        status=TaskStatus.queued,
        progress=0,
        message="Task queued",
    )
    cache.set_json(cache_key, task_id, ttl=settings.cache_ttl_seconds)

    process_video_task.apply_async(
        args=[task_id, url, quality.value, output_format.value],
        task_id=task_id,
    )
    return task_id, False


@celery_app.task(bind=True, name="app.workers.process_video", max_retries=2, default_retry_delay=5)
def process_video_task(
    self: Task,
    task_id: str,
    url: str,
    quality_value: str,
    format_value: str,
) -> dict[str, Any]:
    """Celery task that extracts TikTok video info via yt-dlp."""
    cache = get_cache()
    quality = Quality(quality_value)
    output_format = OutputFormat(format_value)

    _update_task(
        cache,
        task_id,
        status=TaskStatus.processing,
        progress=10,
        message="Starting extraction",
    )

    service = TikTokService()
    try:
        result = service.build_result(url, quality, output_format, task_id)
    except APIError as exc:
        logger.warning("task_failed", task_id=task_id, code=exc.code, message=exc.message)
        _update_task(
            cache,
            task_id,
            status=TaskStatus.failed,
            progress=100,
            message=exc.message,
            error={"code": exc.code, "message": exc.message, "status_code": exc.status_code},
        )
        return {"task_id": task_id, "status": TaskStatus.failed.value, "error": exc.code}
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("task_crashed", task_id=task_id)
        _update_task(
            cache,
            task_id,
            status=TaskStatus.failed,
            progress=100,
            message=str(exc),
            error={"code": "internal_error", "message": str(exc), "status_code": 500},
        )
        return {"task_id": task_id, "status": TaskStatus.failed.value, "error": "internal_error"}

    payload = result.model_dump(mode="json")
    _update_task(
        cache,
        task_id,
        status=TaskStatus.completed,
        progress=100,
        message="Completed",
        result=payload,
    )
    return {"task_id": task_id, "status": TaskStatus.completed.value}
