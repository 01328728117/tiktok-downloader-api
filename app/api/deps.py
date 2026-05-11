"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends

from app.core.cache import CacheBackend, get_cache
from app.core.config import Settings, get_settings
from app.services.tiktok import TikTokService


def settings_dep() -> Settings:
    return get_settings()


def cache_dep() -> CacheBackend:
    return get_cache()


def tiktok_service_dep(settings: Settings = Depends(settings_dep)) -> TikTokService:
    return TikTokService(settings)
