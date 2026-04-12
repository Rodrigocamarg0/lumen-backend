"""
POST /api/chat — SSE streaming persona response.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import state
from app.api.models import ChatRequest

logger = logging.getLogger("routes.chat")
router = APIRouter()

_VALID_PERSONAS = {"kardec"}


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    if request.persona_id not in _VALID_PERSONAS:
        raise HTTPException(
            status_code=404,
            detail=f"Persona '{request.persona_id}' not found. Available: {sorted(_VALID_PERSONAS)}",
        )

    if state.rag is None:
        raise HTTPException(
            status_code=503,
            detail="Index not loaded — run the ingestion pipeline first.",
        )

    from app.llm.engine import is_loaded

    if not is_loaded():
        raise HTTPException(
            status_code=503,
            detail="Model is still loading. Retry after /api/health reports model_loaded=true.",
        )

    async def generate_stream():
        history_dicts = [m.model_dump() for m in request.history]
        try:
            async for event_type, payload in state.rag.astream_response(
                persona_id=request.persona_id,
                message=request.message,
                session_id=request.session_id,
                history=history_dicts,
                max_new_tokens=request.options.max_new_tokens,
                top_k_chunks=request.options.top_k_chunks,
                temperature=request.options.temperature,
            ):
                if event_type == "token":
                    yield f"event: token\ndata: {json.dumps({'token': payload})}\n\n"
                elif event_type == "citations":
                    yield f"event: citations\ndata: {json.dumps({'citations': payload})}\n\n"
                elif event_type == "stats":
                    yield f"event: stats\ndata: {json.dumps({'stats': payload})}\n\n"
                elif event_type == "error":
                    yield f"event: error\ndata: {json.dumps({'detail': payload})}\n\n"
                    return
                elif event_type == "done":
                    yield "event: done\ndata: [DONE]\n\n"
        except Exception as exc:
            logger.exception("Streaming error")
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
