"""GET /api/v1/info endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import cache_dep, tiktok_service_dep
from app.core.cache import CacheBackend
from app.core.exceptions import InvalidTikTokURLError
from app.core.rate_limit import limiter
from app.core.security import require_api_key
from app.schemas.download import TIKTOK_URL_RE, InfoResponse
from app.services.tiktok import TikTokService

router = APIRouter(tags=["info"])


@router.get(
    "/info",
    response_model=InfoResponse,
    summary="Get TikTok video metadata (synchronous)",
    dependencies=[Depends(require_api_key)],
)
@limiter.limit("60/minute")
async def get_info(
    request: Request,
    url: str = Query(..., description="Public TikTok video URL", min_length=10, max_length=2048),
    cache: CacheBackend = Depends(cache_dep),
    service: TikTokService = Depends(tiktok_service_dep),
) -> InfoResponse:
    if not TIKTOK_URL_RE.match(url):
        raise InvalidTikTokURLError("url must be a valid TikTok URL")

    cache_key = f"info:{url}"
    cached = cache.get_json(cache_key)
    if cached:
        return InfoResponse(
            metadata=cached["metadata"], available_formats=cached["formats"], cached=True
        )

    metadata, formats = service.get_full_info(url)
    payload = {"metadata": metadata.model_dump(mode="json"), "formats": formats}
    cache.set_json(cache_key, payload)
    return InfoResponse(metadata=metadata, available_formats=formats, cached=False)
