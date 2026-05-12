"""v1 API routers."""

from fastapi import APIRouter

from app.api.v1 import download, info, proxy, result, status

router = APIRouter(prefix="/api/v1")
router.include_router(download.router)
router.include_router(status.router)
router.include_router(result.router)
router.include_router(info.router)
router.include_router(proxy.router)
