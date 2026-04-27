from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.conversation import (
    ConversationMessage,
    ConversationRun,
    ConversationSession,
    utc_now,
)


def ensure_uuid(value: str) -> str:
    return str(UUID(value))


def get_owned_session(
    db: Session,
    *,
    session_id: str,
    user_id: str,
    include_deleted: bool = False,
) -> ConversationSession | None:
    stmt = select(ConversationSession).where(
        ConversationSession.id == session_id,
        ConversationSession.user_id == user_id,
    )
    if not include_deleted:
        stmt = stmt.where(ConversationSession.status != "deleted")
    return db.execute(stmt).scalar_one_or_none()


def get_or_create_session(
    db: Session,
    *,
    session_id: str | None,
    user_id: str,
    persona_id: str,
    first_message: str,
) -> ConversationSession:
    if session_id:
        normalized_session_id = ensure_uuid(session_id)
        session = get_owned_session(db, session_id=normalized_session_id, user_id=user_id)
        if session is None:
            raise PermissionError("Session not found")
        if session.persona_id != persona_id:
            raise ValueError("Session persona does not match request persona")
        return session

    session = ConversationSession(
        user_id=user_id,
        persona_id=persona_id,
        title=first_message[:80],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def next_message_index(db: Session, session_id: str) -> int:
    stmt = select(func.coalesce(func.max(ConversationMessage.message_index), -1)).where(
        ConversationMessage.session_id == session_id
    )
    return int(db.execute(stmt).scalar_one()) + 1


def persist_completed_turn(
    db: Session,
    *,
    session_id: str,
    user_id: str,
    persona_id: str,
    user_message: str,
    assistant_message: str,
    citations: list | None,
    stats: dict | None,
    trace_id: str,
) -> ConversationRun:
    index = next_message_index(db, session_id)
    now = utc_now()
    db.add_all(
        [
            ConversationMessage(
                session_id=session_id,
                user_id=user_id,
                role="user",
                content=user_message,
                message_index=index,
            ),
            ConversationMessage(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=assistant_message,
                citations=citations,
                stats=stats,
                message_index=index + 1,
            ),
        ]
    )
    run = ConversationRun(
        session_id=session_id,
        user_id=user_id,
        persona_id=persona_id,
        trace_id=trace_id,
        model_provider=settings.LLM_PROVIDER,
        model_id=settings.OPENAI_MODEL,
        status="completed",
        tokens_generated=(stats or {}).get("tokens_generated"),
        tokens_per_second=(stats or {}).get("tokens_per_second"),
        rag_latency_ms=(stats or {}).get("rag_latency_ms"),
        generation_latency_ms=(stats or {}).get("generation_latency_ms"),
        completed_at=now,
    )
    db.add(run)
    session = db.get(ConversationSession, session_id)
    if session is not None:
        session.last_message_at = now
        session.updated_at = now
    db.commit()
    db.refresh(run)
    return run


def persist_failed_run(
    db: Session,
    *,
    session_id: str,
    user_id: str,
    persona_id: str,
    error_detail: str,
    trace_id: str,
) -> None:
    db.add(
        ConversationRun(
            session_id=session_id,
            user_id=user_id,
            persona_id=persona_id,
            trace_id=trace_id,
            model_provider=settings.LLM_PROVIDER,
            model_id=settings.OPENAI_MODEL,
            status="failed",
            error_detail=error_detail,
            completed_at=utc_now(),
        )
    )
    db.commit()


def unix_ts(value: datetime | None) -> int:
    return int(value.timestamp()) if value else 0
