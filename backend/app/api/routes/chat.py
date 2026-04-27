"""
POST /api/chat — SSE streaming persona response.

History is loaded from Agno's PostgresDB (not the request body).
After the stream completes the new turn is persisted back to the DB,
unless `options.incognito=True` — incognito turns are one-shot and never
touch the DB, Agno session store, or memory/summary extraction.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import state
from app.agents.context import update_context_after_turn
from app.agents.registry import get_agent, list_persona_ids
from app.agents.sessions import load_history, save_turn
from app.api.models import ChatRequest
from app.auth.dependencies import require_current_user
from app.auth.models import AuthenticatedUser
from app.db.context import get_relevant_memories, get_session_summary, upsert_session_state
from app.db.conversations import (
    get_or_create_session,
    persist_completed_turn,
    persist_failed_run,
)
from app.db.session import get_db_session

logger = logging.getLogger("routes.chat")
router = APIRouter()
_background_tasks: set[asyncio.Task[None]] = set()


def _schedule_context_update(task: asyncio.Task[None]) -> None:
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@router.post("/chat")
async def chat_endpoint(
    request: ChatRequest,
    http_request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
):
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

    incognito = request.options.incognito
    agent = get_agent(request.persona_id)

    if incognito:
        sid = str(uuid.uuid4())
        history: list[dict[str, str]] = []
        session_summary_text: str | None = None
        session_state_payload: dict = {}
        memory_texts: list[str] = []
    else:
        try:
            conversation = get_or_create_session(
                db,
                session_id=request.session_id,
                user_id=current_user.id,
                persona_id=request.persona_id,
                first_message=request.message,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="Session not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        sid = conversation.id
        history = load_history(agent, sid, max_turns=5)
        summary_record = get_session_summary(db, session_id=sid, user_id=current_user.id)
        session_summary_text = summary_record.summary if summary_record else None
        session_state_record = upsert_session_state(
            db,
            session_id=sid,
            user_id=current_user.id,
            persona_id=request.persona_id,
            updates={
                "answer_mode": request.options.answer_mode,
                "study_goal": request.options.study_goal,
            },
        )
        session_state_payload = session_state_record.state
        memory_texts = [
            memory.memory
            for memory in get_relevant_memories(
                db,
                user_id=current_user.id,
                persona_id=request.persona_id,
                query=request.message,
                limit=5,
            )
        ]

    async def generate_stream():
        assistant_buffer: list[str] = []
        citations: list | None = None
        stats: dict | None = None
        trace_id = getattr(http_request.state, "trace_id", str(uuid.uuid4()))
        yield f"event: session\ndata: {json.dumps({'session_id': sid, 'trace_id': trace_id})}\n\n"
        try:
            async for event_type, payload in state.rag.astream_response(
                persona_id=request.persona_id,
                message=request.message,
                session_id=sid,
                history=history,
                session_summary=session_summary_text,
                user_memories=memory_texts,
                session_state=session_state_payload,
                max_new_tokens=request.options.max_new_tokens,
                top_k_chunks=request.options.top_k_chunks,
                temperature=request.options.temperature,
                reasoning_effort=request.options.reasoning_effort,
            ):
                if event_type == "token":
                    assistant_buffer.append(payload)
                    yield f"event: token\ndata: {json.dumps({'token': payload})}\n\n"
                elif event_type == "citations":
                    citations = payload
                    yield f"event: citations\ndata: {json.dumps({'citations': payload})}\n\n"
                elif event_type == "stats":
                    stats = payload
                    yield f"event: stats\ndata: {json.dumps({'stats': payload})}\n\n"
                elif event_type == "error":
                    logger.error("RAG stream returned error trace_id=%s", trace_id)
                    if not incognito:
                        persist_failed_run(
                            db,
                            session_id=sid,
                            user_id=current_user.id,
                            persona_id=request.persona_id,
                            error_detail=f"RAG stream error trace_id={trace_id}",
                            trace_id=trace_id,
                        )
                    yield (
                        "event: error\n"
                        f"data: {json.dumps({'detail': 'Generation failed', 'trace_id': trace_id})}\n\n"
                    )
                    return
                elif event_type == "done":
                    assistant_content = "".join(assistant_buffer)
                    if not incognito:
                        await save_turn(
                            agent, sid, current_user.id, request.message, assistant_content
                        )
                        persist_completed_turn(
                            db,
                            session_id=sid,
                            user_id=current_user.id,
                            persona_id=request.persona_id,
                            user_message=request.message,
                            assistant_message=assistant_content,
                            citations=citations,
                            stats=stats,
                            trace_id=trace_id,
                        )
                        _schedule_context_update(
                            asyncio.create_task(
                                update_context_after_turn(
                                    session_id=sid,
                                    user_id=current_user.id,
                                    persona_id=request.persona_id,
                                    user_message=request.message,
                                    assistant_message=assistant_content,
                                )
                            )
                        )
                    yield "event: done\ndata: [DONE]\n\n"
        except Exception:
            logger.exception("Streaming error trace_id=%s", trace_id)
            if not incognito:
                try:
                    persist_failed_run(
                        db,
                        session_id=sid,
                        user_id=current_user.id,
                        persona_id=request.persona_id,
                        error_detail=f"Streaming error trace_id={trace_id}",
                        trace_id=trace_id,
                    )
                except Exception:
                    logger.exception("Failed to persist failed run for session %s", sid)
            yield (
                "event: error\n"
                f"data: {json.dumps({'detail': 'Generation failed', 'trace_id': trace_id})}\n\n"
            )

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
