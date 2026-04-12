"""
GET  /api/config     — read current KV cache runtime settings
PUT  /api/config     — update KV cache settings (takes effect on next generation)

No model reload required: TurboQuantCache is created fresh per request,
so settings changes apply immediately on the next chat call.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter()


class KVCacheConfigUpdate(BaseModel):
    enabled: bool | None = None
    bits: float | None = Field(None, ge=1.0, le=8.0)
    outlier_threshold: float | None = Field(None, ge=1.0, le=100.0)


class KVCacheConfigResponse(BaseModel):
    enabled: bool
    bits: float
    outlier_threshold: float


@router.get("/config", response_model=KVCacheConfigResponse)
async def get_config():
    return KVCacheConfigResponse(
        enabled=settings.USE_TURBOQUANT_CACHE,
        bits=settings.KV_CACHE_BITS,
        outlier_threshold=settings.KV_CACHE_OUTLIER_THRESHOLD,
    )


@router.put("/config", response_model=KVCacheConfigResponse)
async def update_config(body: KVCacheConfigUpdate):
    if body.enabled is not None:
        object.__setattr__(settings, "USE_TURBOQUANT_CACHE", body.enabled)
    if body.bits is not None:
        object.__setattr__(settings, "KV_CACHE_BITS", body.bits)
    if body.outlier_threshold is not None:
        object.__setattr__(settings, "KV_CACHE_OUTLIER_THRESHOLD", body.outlier_threshold)
    return KVCacheConfigResponse(
        enabled=settings.USE_TURBOQUANT_CACHE,
        bits=settings.KV_CACHE_BITS,
        outlier_threshold=settings.KV_CACHE_OUTLIER_THRESHOLD,
    )
