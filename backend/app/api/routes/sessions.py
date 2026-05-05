"""
GET/DELETE /api/sessions — session management endpoints.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.registry import get_agent, list_persona_ids
from app.api.models import Message as ChatMessage
from app.api.models import SessionDetail, SessionSummary
from app.auth.dependencies import require_current_user
from app.auth.models import AuthenticatedUser
from app.db.context import delete_session_context
from app.db.conversations import get_owned_session, unix_ts
from app.db.session import get_db_session
from app.models.conversation import ConversationMessage, ConversationSession, utc_now

logger = logging.getLogger("routes.sessions")
router = APIRouter()


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
    persona_id: str | None = None,
    status: str = "active",
) -> list[SessionSummary]:
    """List stored sessions owned by the authenticated user."""
    stmt = select(ConversationSession).where(ConversationSession.user_id == current_user.id)
    if persona_id:
        stmt = stmt.where(ConversationSession.persona_id == persona_id)
    if status:
        stmt = stmt.where(ConversationSession.status == status)
    stmt = stmt.order_by(ConversationSession.updated_at.desc())

    results: list[SessionSummary] = []
    for session in db.execute(stmt).scalars():
        preview_stmt = (
            select(ConversationMessage.content)
            .where(
                ConversationMessage.session_id == session.id,
                ConversationMessage.role == "user",
            )
            .order_by(ConversationMessage.message_index.desc())
            .limit(1)
        )
        turn_count_stmt = select(func.count()).where(
            ConversationMessage.session_id == session.id,
            ConversationMessage.role == "user",
        )
        results.append(
            SessionSummary(
                session_id=session.id,
                persona_id=session.persona_id,
                created_at=unix_ts(session.created_at),
                updated_at=unix_ts(session.updated_at),
                turn_count=int(db.execute(turn_count_stmt).scalar_one()),
                preview=(db.execute(preview_stmt).scalar_one_or_none() or "")[:120],
                title=session.title,
                status=session.status,
            )
        )
    return results


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> SessionDetail:
    """Return the app-level message history for an owned session."""
    session = get_owned_session(db, session_id=session_id, user_id=current_user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = (
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session.id)
        .order_by(ConversationMessage.message_index)
    )
    turns = [
        ChatMessage(role=message.role, content=message.content, citations=message.citations)
        for message in db.execute(stmt).scalars()
        if message.role in ("user", "assistant") and message.content
    ]
    return SessionDetail(session_id=session.id, persona_id=session.persona_id, turns=turns)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> None:
    """Soft-delete an owned app session and delete matching Agno history."""
    session = get_owned_session(db, session_id=session_id, user_id=current_user.id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    session.status = "deleted"
    session.updated_at = utc_now()
    db.commit()
    delete_session_context(db, session_id=session.id, user_id=current_user.id)

    if session.persona_id in list_persona_ids():
        agent = get_agent(session.persona_id)
        try:
            agent.delete_session(session_id=session.id)
        except Exception:
            logger.exception("Failed to delete Agno session %s", session.id)
