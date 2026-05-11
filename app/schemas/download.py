"""Pydantic v2 schemas for TikTok download API."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

TIKTOK_URL_RE = re.compile(
    r"^https?://" r"(?:(?:www|m|vm|vt)\.)?" r"(?:tiktok\.com|douyin\.com)" r"/.+",
    re.IGNORECASE,
)


class Quality(StrEnum):
    """Requested output quality bucket."""

    high = "high"
    medium = "medium"
    low = "low"


class OutputFormat(StrEnum):
    mp4 = "mp4"
    mp3 = "mp3"


class TaskStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class DownloadRequest(BaseModel):
    """Body for POST /api/v1/download."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str = Field(..., description="Public TikTok video URL", min_length=10, max_length=2048)
    quality: Quality = Field(default=Quality.high, description="high|medium|low")
    format: OutputFormat = Field(
        default=OutputFormat.mp4,
        description="Output container — mp4 (video) or mp3 (audio only)",
    )

    @field_validator("url")
    @classmethod
    def _validate_tiktok_url(cls, v: str) -> str:
        if not TIKTOK_URL_RE.match(v):
            raise ValueError(
                "url must be a valid TikTok URL (e.g. https://www.tiktok.com/@user/video/123)"
            )
        return v


class DownloadResponse(BaseModel):
    """Response from POST /api/v1/download."""

    task_id: str
    status: TaskStatus = TaskStatus.queued
    cached: bool = False
    poll_url: str
    result_url: str


class StatusResponse(BaseModel):
    """Response from GET /api/v1/status/{task_id}."""

    task_id: str
    status: TaskStatus
    progress: int = Field(default=0, ge=0, le=100)
    message: str | None = None
    error: dict[str, Any] | None = None
    updated_at: float
    result_url: str | None = None


class VideoMetadata(BaseModel):
    """Metadata extracted from a TikTok video."""

    id: str
    title: str
    author: str | None = None
    author_url: HttpUrl | None = None
    duration: float | None = None
    thumbnail: HttpUrl | None = None
    view_count: int | None = None
    like_count: int | None = None
    upload_date: str | None = None
    description: str | None = None
    source_url: HttpUrl | None = None


class DownloadResult(BaseModel):
    """Final extraction result returned by GET /api/v1/result/{task_id}."""

    task_id: str
    status: TaskStatus = TaskStatus.completed
    metadata: VideoMetadata
    download_url: HttpUrl
    audio_url: HttpUrl | None = None
    format: OutputFormat = OutputFormat.mp4
    quality: Quality
    width: int | None = None
    height: int | None = None
    filesize: int | None = None
    watermark_free: bool = True
    expires_at: float | None = None


class InfoResponse(BaseModel):
    """Response from GET /api/v1/info?url=..."""

    metadata: VideoMetadata
    available_formats: list[dict[str, Any]] = Field(default_factory=list)
    cached: bool = False


class HealthResponse(BaseModel):
    """Response from GET /health."""

    status: str = "ok"
    version: str
    environment: str
    cache: dict[str, Any]
    celery_eager: bool
