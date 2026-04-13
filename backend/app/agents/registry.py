"""
Persona agent registry.

Call build_registry() once at application startup.  After that, get_agent()
and list_persona_ids() are safe to call from any route handler.
"""

from __future__ import annotations

from agno.agent import Agent

from app.agents.kardec import make_kardec_agent

_registry: dict[str, Agent] = {}


def build_registry() -> None:
    """Instantiate all persona agents and register them. Call once at startup."""
    _registry["kardec"] = make_kardec_agent()


def get_agent(persona_id: str) -> Agent:
    if persona_id not in _registry:
        raise KeyError(f"Unknown persona: {persona_id!r}. Available: {list(_registry)}")
    return _registry[persona_id]


def list_persona_ids() -> list[str]:
    return list(_registry.keys())
