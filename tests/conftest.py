"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _env_setup(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Reset env + singletons before each test."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("API_KEYS", "test-key")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.setenv("CACHE_TTL_SECONDS", "60")

    from app.core import cache as cache_module
    from app.core import config as config_module

    config_module.reset_settings_cache()
    cache_module.reset_cache_singleton()

    yield

    config_module.reset_settings_cache()
    cache_module.reset_cache_singleton()


@pytest.fixture
def sample_info() -> dict[str, Any]:
    """A minimal yt-dlp-shaped info dict for tests."""
    return {
        "id": "7000000000000000001",
        "title": "Test TikTok Video",
        "uploader": "@testuser",
        "uploader_url": "https://www.tiktok.com/@testuser",
        "duration": 12.5,
        "thumbnail": "https://example.com/thumb.jpg",
        "view_count": 1000,
        "like_count": 200,
        "upload_date": "20240101",
        "description": "Hello world",
        "webpage_url": "https://www.tiktok.com/@testuser/video/7000000000000000001",
        "formats": [
            {
                "format_id": "play_addr_no_watermark",
                "ext": "mp4",
                "width": 1080,
                "height": 1920,
                "filesize": 1500000,
                "vcodec": "h264",
                "acodec": "aac",
                "tbr": 2500,
                "url": "https://cdn.example.com/no_wm.mp4",
            },
            {
                "format_id": "download_addr_watermark",
                "ext": "mp4",
                "width": 720,
                "height": 1280,
                "filesize": 800000,
                "vcodec": "h264",
                "acodec": "aac",
                "tbr": 1500,
                "url": "https://cdn.example.com/wm.mp4?watermark=1",
                "format_note": "watermark",
            },
            {
                "format_id": "audio_only",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "aac",
                "abr": 128,
                "url": "https://cdn.example.com/audio.m4a",
            },
            {
                "format_id": "mid",
                "ext": "mp4",
                "width": 540,
                "height": 720,
                "vcodec": "h264",
                "acodec": "aac",
                "tbr": 1000,
                "url": "https://cdn.example.com/mid.mp4",
            },
        ],
    }


@pytest.fixture
def patched_ytdlp(monkeypatch: pytest.MonkeyPatch, sample_info: dict[str, Any]) -> dict[str, Any]:
    """Patch yt_dlp.YoutubeDL to return ``sample_info`` without network access."""

    class FakeYDL:
        def __init__(self, opts: dict[str, Any] | None = None) -> None:
            self.opts = opts or {}

        def __enter__(self) -> FakeYDL:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
            if "404" in url or "deleted" in url:
                from yt_dlp.utils import DownloadError

                raise DownloadError("Video unavailable: removed")
            if "private" in url:
                from yt_dlp.utils import DownloadError

                raise DownloadError("This video is private")
            return sample_info

    import yt_dlp

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    return sample_info


@pytest.fixture
def client(patched_ytdlp: dict[str, Any]) -> Iterator[TestClient]:
    """FastAPI TestClient with patched yt-dlp and clean cache."""
    from app.core.cache import get_cache
    from app.main import create_app

    app = create_app()
    get_cache().clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": "test-key"}
