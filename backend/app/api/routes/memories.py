"""
GET/DELETE /api/memories — user-controlled long-term memories.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.models import UserMemoryResponse
from app.auth.dependencies import require_current_user
from app.auth.models import AuthenticatedUser
from app.db.context import list_active_memories, soft_delete_memory
from app.db.conversations import unix_ts
from app.db.session import get_db_session

router = APIRouter()


@router.get("/memories", response_model=list[UserMemoryResponse])
def list_memories(
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
    persona_id: str | None = None,
) -> list[UserMemoryResponse]:
    memories = list_active_memories(db, user_id=current_user.id, persona_id=persona_id, limit=100)
    return [
        UserMemoryResponse(
            id=memory.id,
            persona_id=memory.persona_id,
            memory=memory.memory,
            topics=[str(topic) for topic in memory.topics or []],
            confidence=memory.confidence,
            source_session_id=memory.source_session_id,
            created_at=unix_ts(memory.created_at),
            updated_at=unix_ts(memory.updated_at),
        )
        for memory in memories
    ]


@router.delete("/memories/{memory_id}", status_code=204, response_class=Response)
def delete_memory(
    memory_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
    db: Annotated[Session, Depends(get_db_session)],
) -> None:
    if not soft_delete_memory(db, memory_id=memory_id, user_id=current_user.id):
        raise HTTPException(status_code=404, detail="Memory not found")
