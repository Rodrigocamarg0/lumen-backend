"""
Agno session helpers: load chat history from PostgresDB and persist new turns.

Generation is handled entirely by rag.astream_response(); these helpers only
read/write to the Agno session store without triggering any LLM calls.
"""

from __future__ import annotations

import logging
import time
import uuid

from agno.agent import Agent

logger = logging.getLogger("agents.sessions")


def load_history(
    agent: Agent,
    session_id: str,
    max_turns: int = 10,
) -> list[dict[str, str]]:
    """
    Load the last `max_turns` user+assistant exchanges from PostgresDB.
    Returns a list of {"role": ..., "content": ...} dicts ready to be
    passed to rag.astream_response(history=...).
    """
    try:
        messages = agent.get_chat_history(session_id=session_id, last_n_runs=max_turns)
        return [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant") and m.content
        ]
    except Exception:
        logger.exception("Failed to load history for session %s", session_id)
        return []


async def save_turn(
    agent: Agent,
    session_id: str,
    user_id: str,
    user_message: str,
    assistant_content: str,
) -> None:
    """
    Persist one completed user→assistant exchange to PostgresDB.
    Builds a RunOutput directly — no LLM call is triggered.
    """
    try:
        # Import low-level Agno types here so startup doesn't fail if agno is
        # not yet installed.
        from agno.models.message import Message  # type: ignore[import]
        from agno.run.agent import RunOutput  # type: ignore[import]
        from agno.run.base import RunStatus  # type: ignore[import]
        from agno.session.agent import AgentSession  # type: ignore[import]

        session: AgentSession | None = agent.get_session(session_id=session_id)
        if session is None:
            session = AgentSession(
                session_id=session_id,
                agent_id=agent.id,
                user_id=user_id,
                agent_data={"agent_id": agent.id, "name": agent.name},
            )
        elif not session.user_id:
            session.user_id = user_id

        run = RunOutput(
            run_id=str(uuid.uuid4()),
            agent_id=agent.id,
            session_id=session_id,
            user_id=user_id,
            messages=[
                Message(role="user", content=user_message),
                Message(role="assistant", content=assistant_content),
            ],
            content=assistant_content,
            status=RunStatus.completed,
            created_at=int(time.time()),
        )
        session.upsert_run(run)
        await agent.asave_session(session)

    except Exception:
        logger.exception("Failed to save turn for session %s", session_id)
