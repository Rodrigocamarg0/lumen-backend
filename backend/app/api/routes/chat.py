"""
POST /api/chat — SSE streaming persona response.

History is loaded from Agno's PostgresDB (not the request body).
After the stream completes the new turn is persisted back to the DB.
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import state
from app.agents.registry import get_agent, list_persona_ids
from app.agents.sessions import load_history, save_turn
from app.api.models import ChatRequest

logger = logging.getLogger("routes.chat")
router = APIRouter()


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    if request.persona_id not in list_persona_ids():
        raise HTTPException(
            status_code=404,
            detail=f"Persona '{request.persona_id}' not found. Available: {list_persona_ids()}",
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

    agent = get_agent(request.persona_id)
    sid = request.session_id or str(uuid.uuid4())
    history = load_history(agent, sid, max_turns=10)

    async def generate_stream():
        assistant_buffer: list[str] = []
        try:
            async for event_type, payload in state.rag.astream_response(
                persona_id=request.persona_id,
                message=request.message,
                session_id=sid,
                history=history,
                max_new_tokens=request.options.max_new_tokens,
                top_k_chunks=request.options.top_k_chunks,
                temperature=request.options.temperature,
            ):
                if event_type == "token":
                    assistant_buffer.append(payload)
                    yield f"event: token\ndata: {json.dumps({'token': payload})}\n\n"
                elif event_type == "citations":
                    yield f"event: citations\ndata: {json.dumps({'citations': payload})}\n\n"
                elif event_type == "stats":
                    yield f"event: stats\ndata: {json.dumps({'stats': payload})}\n\n"
                elif event_type == "error":
                    yield f"event: error\ndata: {json.dumps({'detail': payload})}\n\n"
                    return
                elif event_type == "done":
                    await save_turn(agent, sid, request.message, "".join(assistant_buffer))
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
