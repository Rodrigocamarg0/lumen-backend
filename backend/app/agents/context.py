from __future__ import annotations

import logging

from app.db.context import add_user_memory, get_session_summary, upsert_session_summary
from app.db.session import SessionLocal
from app.llm.context import extract_user_memories, summarize_session

logger = logging.getLogger("agents.context")


async def update_context_after_turn(
    *,
    session_id: str,
    user_id: str,
    persona_id: str,
    user_message: str,
    assistant_message: str,
) -> None:
    db = SessionLocal()
    try:
        previous = get_session_summary(db, session_id=session_id, user_id=user_id)
        summary, topics = await summarize_session(
            previous_summary=previous.summary if previous else None,
            user_message=user_message,
            assistant_message=assistant_message,
        )
        if summary:
            upsert_session_summary(
                db,
                session_id=session_id,
                user_id=user_id,
                persona_id=persona_id,
                summary=summary,
                topics=topics,
            )

        for extracted in await extract_user_memories(
            user_message=user_message,
            assistant_message=assistant_message,
        ):
            add_user_memory(
                db,
                user_id=user_id,
                persona_id=persona_id,
                memory=extracted["memory"],
                topics=extracted["topics"],
                confidence=extracted["confidence"],
                source_session_id=session_id,
            )
    except Exception:
        logger.exception("Failed to update memory/summary context for session %s", session_id)
    finally:
        db.close()
