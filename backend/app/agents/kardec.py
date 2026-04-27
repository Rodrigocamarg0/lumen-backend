"""
Kardec persona as an Agno Agent.

The Agent carries identity (id, name, description, system prompt) and owns the
PostgresDb connection for session persistence.  It does NOT call agent.run() —
generation goes through rag.astream_response(). Agno is used only for history
storage and retrieval.
"""

from __future__ import annotations

from agno.agent import Agent
from agno.models.openai import OpenAIChat

from app.agents.db import get_db
from app.config import settings
from app.persona.prompts import get_prompt


def make_kardec_agent() -> Agent:
    # model= is required by Agno's constructor but is never called for inference
    # here — generation happens in rag.astream_response(). We configure it to
    # match the external OpenAI provider so Agno initialises without errors.
    model = OpenAIChat(id=settings.OPENAI_MODEL)

    return Agent(
        id="kardec",
        name="Allan Kardec",
        model=model,
        description="Allan Kardec — codificador da Doutrina Espírita",
        instructions=get_prompt("kardec"),
        db=get_db(),
        # History injection is done manually in sessions.load_history(); Agno
        # must not inject it automatically (it would call the model).
        add_history_to_context=False,
        # Disabled: known Agno bug causes datetime serialization error with
        # PostgresDb when this is True (github.com/agno-agi/agno#5661).
        add_datetime_to_context=False,
    )
