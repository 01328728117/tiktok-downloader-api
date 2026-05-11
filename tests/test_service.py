"""Unit tests for the TikTok service layer + helpers."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.cache import CacheBackend
from app.core.exceptions import VideoPrivateError, VideoUnavailableError
from app.schemas.download import OutputFormat, Quality
from app.services.tiktok import TikTokService, _strip_watermark_url


def test_strip_watermark_url_removes_flag() -> None:
    assert "watermark" not in _strip_watermark_url("https://x/y?watermark=1&a=2")
    assert "watermark" not in _strip_watermark_url("https://x/y?watermark=1")
    assert _strip_watermark_url("https://x/y") == "https://x/y"


def test_service_picks_no_watermark_high_quality(patched_ytdlp: dict[str, Any]) -> None:
    service = TikTokService()
    result = service.build_result(
        "https://www.tiktok.com/@u/video/1",
        Quality.high,
        OutputFormat.mp4,
        task_id="t1",
    )
    assert result.download_url
    assert "watermark" not in str(result.download_url)
    assert result.metadata.author == "@testuser"
    assert result.height == 1920
    assert result.audio_url


def test_service_low_quality_picks_lowest_height(patched_ytdlp: dict[str, Any]) -> None:
    service = TikTokService()
    result = service.build_result(
        "https://www.tiktok.com/@u/video/2",
        Quality.low,
        OutputFormat.mp4,
        task_id="t2",
    )
    assert result.height is not None and result.height <= 1280


def test_service_mp3_returns_audio_only(patched_ytdlp: dict[str, Any]) -> None:
    service = TikTokService()
    result = service.build_result(
        "https://www.tiktok.com/@u/video/3",
        Quality.high,
        OutputFormat.mp3,
        task_id="t3",
    )
    assert str(result.download_url).endswith(".m4a")
    assert result.format == OutputFormat.mp3


def test_service_classifies_private(patched_ytdlp: dict[str, Any]) -> None:
    service = TikTokService()
    with pytest.raises(VideoPrivateError):
        service.extract("https://www.tiktok.com/@u/video/private")


def test_service_classifies_unavailable(patched_ytdlp: dict[str, Any]) -> None:
    service = TikTokService()
    with pytest.raises(VideoUnavailableError):
        service.extract("https://www.tiktok.com/@u/video/404")


def test_service_get_metadata(patched_ytdlp: dict[str, Any]) -> None:
    md = TikTokService().get_metadata("https://www.tiktok.com/@u/video/m")
    assert md.title == "Test TikTok Video"
    assert md.duration == 12.5


def test_cache_backend_memory_roundtrip() -> None:
    cache = CacheBackend()
    cache.set_json("foo", {"bar": 1})
    assert cache.get_json("foo") == {"bar": 1}
    cache.delete("foo")
    assert cache.get_json("foo") is None
    assert cache.ping()["ok"] is True
    assert cache.backend in {"memory", "redis"}
