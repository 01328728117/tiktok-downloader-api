"""TikTok extraction service powered by yt-dlp."""

from __future__ import annotations

import re
from typing import Any

import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    APIError,
    ExtractionError,
    InvalidTikTokURLError,
    VideoPrivateError,
    VideoUnavailableError,
)
from app.core.logging import get_logger
from app.schemas.download import (
    DownloadResult,
    OutputFormat,
    Quality,
    TaskStatus,
    VideoMetadata,
)

logger = get_logger(__name__)


QUALITY_FORMAT_MAP: dict[Quality, str] = {
    Quality.high: "bv*+ba/b",
    Quality.medium: "best[height<=720]/best",
    Quality.low: "best[height<=480]/worst",
}


_PRIVATE_PATTERNS = (
    "private",
    "login required",
    "this video is not available",
    "sign in to confirm",
)
_UNAVAILABLE_PATTERNS = (
    "video unavailable",
    "removed",
    "not found",
    "404",
    "deleted",
)

_NO_WATERMARK_TOKENS = (
    "no_watermark",
    "no-watermark",
    "without_watermark",
    "without-watermark",
    "nowm",
    "no wm",
)


def _classify_error(msg: str) -> type[APIError]:
    m = msg.lower()
    if any(p in m for p in _PRIVATE_PATTERNS):
        return VideoPrivateError
    if any(p in m for p in _UNAVAILABLE_PATTERNS):
        return VideoUnavailableError
    return ExtractionError


def _strip_watermark_url(url: str) -> str:
    """Best-effort transformation toward watermark-free TikTok URLs.

    yt-dlp already prefers watermark-free formats when available; this is a
    secondary safeguard that removes the ``watermark=1`` query flag if present.
    """
    return re.sub(r"([?&])watermark=1(&|$)", r"\1", url).rstrip("?&")


class TikTokService:
    """Wrapper around yt-dlp for TikTok metadata + URL extraction."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _base_opts(self) -> dict[str, Any]:
        return {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": self._settings.ytdlp_socket_timeout,
            "retries": self._settings.ytdlp_retries,
            "extractor_retries": self._settings.ytdlp_retries,
            "user_agent": self._settings.ytdlp_user_agent,
            "extractor_args": {
                "tiktok": {
                    # prefer non-watermarked download endpoints when available
                    "api_hostname": ["api16-normal-c-useast1a.tiktokv.com"],
                }
            },
        }

    def extract(self, url: str) -> dict[str, Any]:
        """Run yt-dlp to extract video info. Returns the raw info dict."""
        if not url:
            raise InvalidTikTokURLError("url is required")

        opts = self._base_opts()
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except (DownloadError, ExtractorError) as exc:
            msg = str(exc)
            logger.warning("ytdlp_extract_failed", url=url, error=msg)
            err_cls = _classify_error(msg)
            raise err_cls(f"Failed to extract TikTok video: {msg}") from exc
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("ytdlp_unexpected", url=url)
            raise ExtractionError(f"Unexpected error: {exc}") from exc

        if info is None:
            raise VideoUnavailableError("No video data returned from extractor")

        if info.get("entries"):
            info = info["entries"][0]

        return info

    def get_metadata(self, url: str) -> VideoMetadata:
        info = self.extract(url)
        return self._build_metadata(info)

    def get_full_info(self, url: str) -> tuple[VideoMetadata, list[dict[str, Any]]]:
        info = self.extract(url)
        metadata = self._build_metadata(info)
        formats = self._summarize_formats(info)
        return metadata, formats

    def build_result(
        self,
        url: str,
        quality: Quality,
        output_format: OutputFormat,
        task_id: str,
    ) -> DownloadResult:
        info = self.extract(url)
        metadata = self._build_metadata(info)
        chosen = self._pick_format(info, quality, output_format)
        if not chosen:
            raise ExtractionError("No suitable download URL found")

        audio_url = self._pick_audio(info) if output_format == OutputFormat.mp4 else None

        download_url = _strip_watermark_url(chosen.get("url", ""))
        if not download_url:
            raise ExtractionError("Download URL missing from extractor output")

        return DownloadResult(
            task_id=task_id,
            status=TaskStatus.completed,
            metadata=metadata,
            download_url=download_url,  # type: ignore[arg-type]
            audio_url=audio_url,  # type: ignore[arg-type]
            format=output_format,
            quality=quality,
            width=chosen.get("width"),
            height=chosen.get("height"),
            filesize=chosen.get("filesize") or chosen.get("filesize_approx"),
            watermark_free=True,
        )

    # ----- helpers -----

    def _build_metadata(self, info: dict[str, Any]) -> VideoMetadata:
        author = info.get("uploader") or info.get("creator") or info.get("channel")
        author_url = info.get("uploader_url") or info.get("channel_url")
        return VideoMetadata(
            id=str(info.get("id") or info.get("display_id") or "unknown"),
            title=info.get("title") or info.get("description") or "TikTok video",
            author=author,
            author_url=author_url,
            duration=info.get("duration"),
            thumbnail=info.get("thumbnail"),
            view_count=info.get("view_count"),
            like_count=info.get("like_count"),
            upload_date=info.get("upload_date"),
            description=info.get("description"),
            source_url=info.get("webpage_url") or info.get("original_url"),
        )

    def _summarize_formats(self, info: dict[str, Any]) -> list[dict[str, Any]]:
        formats = info.get("formats") or []
        summary = []
        for fmt in formats:
            summary.append(
                {
                    "format_id": fmt.get("format_id"),
                    "ext": fmt.get("ext"),
                    "width": fmt.get("width"),
                    "height": fmt.get("height"),
                    "filesize": fmt.get("filesize") or fmt.get("filesize_approx"),
                    "vcodec": fmt.get("vcodec"),
                    "acodec": fmt.get("acodec"),
                    "tbr": fmt.get("tbr"),
                }
            )
        return summary

    @staticmethod
    def _is_watermarked(fmt: dict[str, Any]) -> bool:
        """Detect TikTok formats that carry a visible watermark overlay.

        TikTok's yt-dlp extractor labels watermark-free streams with ids/notes
        like ``play_addr_no_watermark`` — treat those as NOT watermarked.
        """
        haystack = (
            " ".join((str(fmt.get("format_id") or ""), str(fmt.get("format_note") or "")))
            .lower()
            .strip()
        )
        if not haystack:
            return False
        if any(token in haystack for token in _NO_WATERMARK_TOKENS):
            return False
        return "watermark" in haystack or "_wm" in haystack

    def _pick_format(
        self,
        info: dict[str, Any],
        quality: Quality,
        output_format: OutputFormat,
    ) -> dict[str, Any] | None:
        if output_format == OutputFormat.mp3:
            audio = self._pick_audio(info)
            if audio:
                return {
                    "url": str(audio),
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "aac",
                }
            # No audio-only stream — fall back to mp4 (clients can extract
            # audio with ffmpeg). TikTok mp4s embed AAC audio so it works.
            video_fallback = self._pick_video_format(info, quality)
            if video_fallback:
                return {
                    "url": video_fallback.get("url"),
                    "ext": video_fallback.get("ext", "mp4"),
                    "vcodec": video_fallback.get("vcodec"),
                    "acodec": video_fallback.get("acodec") or "aac",
                }
            return None

        return self._pick_video_format(info, quality)

    def _pick_video_format(self, info: dict[str, Any], quality: Quality) -> dict[str, Any] | None:
        formats = info.get("formats") or []
        video_formats = [f for f in formats if f.get("vcodec") not in (None, "none")]
        clean = [f for f in video_formats if not self._is_watermarked(f)]
        candidates = clean or video_formats

        if not candidates and info.get("url"):
            return {"url": info["url"], "ext": "mp4"}
        if not candidates:
            return None

        if quality == Quality.high:
            candidates.sort(
                key=lambda f: (f.get("height") or 0, f.get("tbr") or 0),
                reverse=True,
            )
        elif quality == Quality.medium:
            candidates.sort(
                key=lambda f: abs((f.get("height") or 0) - 720),
            )
        else:  # low
            candidates.sort(key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))

        return candidates[0]

    def _pick_audio(self, info: dict[str, Any]) -> str | None:
        formats = info.get("formats") or []
        audio_only = [
            f
            for f in formats
            if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none")
        ]
        if audio_only:
            audio_only.sort(key=lambda f: f.get("abr") or 0, reverse=True)
            return audio_only[0].get("url")
        return None


def get_tiktok_service() -> TikTokService:
    """FastAPI dependency factory."""
    return TikTokService()
