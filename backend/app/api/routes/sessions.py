"""
GET/DELETE /api/sessions — session management endpoints.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.agents.registry import get_agent, list_persona_ids
from app.api.models import Message as ChatMessage
from app.api.models import SessionDetail, SessionSummary

logger = logging.getLogger("routes.sessions")
router = APIRouter()


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(persona_id: str | None = None) -> list[SessionSummary]:
    """List all stored sessions, optionally filtered by persona."""
    persona_ids = [persona_id] if persona_id else list_persona_ids()
    results: list[SessionSummary] = []

    for pid in persona_ids:
        try:
            agent = get_agent(pid)
        except KeyError:
            continue
        try:
            sessions = agent.db.get_all_sessions(agent_id=pid)
            for session in sessions:
                results.append(SessionSummary.from_agno(session, pid))
        except Exception:
            logger.exception("Failed to list sessions for persona %s", pid)

    results.sort(key=lambda s: s.updated_at, reverse=True)
    return results


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: str) -> SessionDetail:
    """Return the full turn history for a session."""
    for pid in list_persona_ids():
        agent = get_agent(pid)
        try:
            session = agent.get_session(session_id=session_id)
        except Exception:
            continue
        if session is None:
            continue

        turns = [
            ChatMessage(role=m.role, content=m.content or "")
            for m in session.get_chat_history()
            if m.role in ("user", "assistant") and m.content
        ]
        return SessionDetail(session_id=session_id, persona_id=pid, turns=turns)

    raise HTTPException(status_code=404, detail="Session not found")


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str) -> None:
    """Delete a session and all its history."""
    for pid in list_persona_ids():
        agent = get_agent(pid)
        try:
            session = agent.get_session(session_id=session_id)
        except Exception:
            continue
        if session is not None:
            agent.delete_session(session_id=session_id)
            return

    raise HTTPException(status_code=404, detail="Session not found")
