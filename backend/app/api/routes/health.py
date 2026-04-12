from fastapi import APIRouter

from app import state
from app.api.models import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    from app.llm.engine import is_loaded, vram_info

    model_loaded = is_loaded()
    index_loaded = state.rag is not None and state.rag.index.is_ready()
    vram_used, vram_total = vram_info()

    persona_available: list[str] = []
    if model_loaded and index_loaded:
        persona_available = ["kardec"]

    if model_loaded and index_loaded:
        status = "ok"
    elif index_loaded or model_loaded:
        status = "degraded"
    else:
        status = "error"

    return HealthResponse(
        status=status,
        model_loaded=model_loaded,
        index_loaded=index_loaded,
        persona_available=persona_available,
        vram_used_mb=vram_used,
        vram_total_mb=vram_total,
        version="1.0.0",
    )
