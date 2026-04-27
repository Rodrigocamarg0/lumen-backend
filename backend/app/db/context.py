from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.conversation import (
    ConversationMessage,
    ConversationSessionState,
    ConversationSessionSummary,
    UserMemory,
    utc_now,
)


def get_session_summary(
    db: Session,
    *,
    session_id: str,
    user_id: str,
) -> ConversationSessionSummary | None:
    stmt = select(ConversationSessionSummary).where(
        ConversationSessionSummary.session_id == session_id,
        ConversationSessionSummary.user_id == user_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def upsert_session_summary(
    db: Session,
    *,
    session_id: str,
    user_id: str,
    persona_id: str,
    summary: str,
    topics: list[str],
) -> ConversationSessionSummary:
    turn_count = int(
        db.execute(
            select(func.count()).where(
                ConversationMessage.session_id == session_id,
                ConversationMessage.role == "user",
            )
        ).scalar_one()
    )
    now = utc_now()
    stored = get_session_summary(db, session_id=session_id, user_id=user_id)
    if stored is None:
        stored = ConversationSessionSummary(
            session_id=session_id,
            user_id=user_id,
            persona_id=persona_id,
            summary=summary,
            topics=topics,
            turn_count=turn_count,
        )
        db.add(stored)
    else:
        stored.summary = summary
        stored.topics = topics
        stored.turn_count = turn_count
        stored.updated_at = now
    db.commit()
    db.refresh(stored)
    return stored


def get_session_state(
    db: Session,
    *,
    session_id: str,
    user_id: str,
) -> ConversationSessionState | None:
    stmt = select(ConversationSessionState).where(
        ConversationSessionState.session_id == session_id,
        ConversationSessionState.user_id == user_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def upsert_session_state(
    db: Session,
    *,
    session_id: str,
    user_id: str,
    persona_id: str,
    updates: dict,
) -> ConversationSessionState:
    current = get_session_state(db, session_id=session_id, user_id=user_id)
    merged = dict(current.state if current else {})
    merged.update({key: value for key, value in updates.items() if value not in (None, "")})

    if current is None:
        current = ConversationSessionState(
            session_id=session_id,
            user_id=user_id,
            persona_id=persona_id,
            state=merged,
        )
        db.add(current)
    else:
        current.state = merged
        current.updated_at = utc_now()
    db.commit()
    db.refresh(current)
    return current


def list_active_memories(
    db: Session,
    *,
    user_id: str,
    persona_id: str | None = None,
    limit: int = 20,
) -> list[UserMemory]:
    stmt = select(UserMemory).where(
        UserMemory.user_id == user_id,
        UserMemory.is_active.is_(True),
    )
    if persona_id:
        stmt = stmt.where(UserMemory.persona_id == persona_id)
    stmt = stmt.order_by(UserMemory.updated_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars())


def get_relevant_memories(
    db: Session,
    *,
    user_id: str,
    persona_id: str,
    query: str,
    limit: int = 5,
) -> list[UserMemory]:
    memories = list_active_memories(db, user_id=user_id, persona_id=persona_id, limit=50)
    if not memories:
        return []

    query_terms = {term.lower() for term in query.split() if len(term) > 3}

    def score(memory: UserMemory) -> tuple[int, float]:
        text = f"{memory.memory} {' '.join(memory.topics or [])}".lower()
        overlap = sum(1 for term in query_terms if term in text)
        return overlap, memory.confidence

    return sorted(memories, key=score, reverse=True)[:limit]


def add_user_memory(
    db: Session,
    *,
    user_id: str,
    persona_id: str,
    memory: str,
    topics: list[str],
    confidence: float,
    source_session_id: str,
) -> UserMemory | None:
    normalized = " ".join(memory.split())
    if not normalized:
        return None

    existing_stmt = select(UserMemory).where(
        UserMemory.user_id == user_id,
        UserMemory.persona_id == persona_id,
        UserMemory.is_active.is_(True),
    )
    for existing in db.execute(existing_stmt).scalars():
        if existing.memory.strip().lower() == normalized.lower():
            existing.topics = topics or existing.topics
            existing.confidence = max(existing.confidence, confidence)
            existing.source_session_id = source_session_id
            existing.updated_at = utc_now()
            db.commit()
            db.refresh(existing)
            return existing

    stored = UserMemory(
        user_id=user_id,
        persona_id=persona_id,
        memory=normalized,
        topics=topics,
        confidence=confidence,
        source_session_id=source_session_id,
    )
    db.add(stored)
    db.commit()
    db.refresh(stored)
    return stored


def soft_delete_memory(db: Session, *, memory_id: str, user_id: str) -> bool:
    stmt = select(UserMemory).where(
        UserMemory.id == memory_id,
        UserMemory.user_id == user_id,
        UserMemory.is_active.is_(True),
    )
    memory = db.execute(stmt).scalar_one_or_none()
    if memory is None:
        return False
    memory.is_active = False
    memory.updated_at = utc_now()
    db.commit()
    return True


def delete_session_context(db: Session, *, session_id: str, user_id: str) -> None:
    summary = get_session_summary(db, session_id=session_id, user_id=user_id)
    if summary is not None:
        db.delete(summary)

    state = get_session_state(db, session_id=session_id, user_id=user_id)
    if state is not None:
        db.delete(state)

    stmt = select(UserMemory).where(
        UserMemory.user_id == user_id,
        UserMemory.source_session_id == session_id,
        UserMemory.is_active.is_(True),
    )
    for memory in db.execute(stmt).scalars():
        memory.is_active = False
        memory.updated_at = utc_now()
    db.commit()
