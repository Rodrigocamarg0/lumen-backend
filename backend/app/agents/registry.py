"""
Persona agent registry.

Call build_registry() once at application startup.  After that, get_agent()
and list_persona_ids() are safe to call from any route handler.
"""

from __future__ import annotations

from app.config import settings
from app.persona.catalog import parse_enabled_personas

_registry: dict[str, object] = {}


def build_registry() -> None:
    """Instantiate all persona agents and register them. Call once at startup."""
    from app.agents.kardec import make_kardec_agent

    agent_factories = {
        "kardec": make_kardec_agent,
    }
    _registry.clear()
    enabled_ids = parse_enabled_personas(settings.ENABLED_PERSONAS)
    for persona_id in enabled_ids:
        factory = agent_factories.get(persona_id)
        if factory is not None:
            _registry[persona_id] = factory()


def get_agent(persona_id: str) -> object:
    if persona_id not in _registry:
        raise KeyError(f"Unknown persona: {persona_id!r}. Available: {list(_registry)}")
    return _registry[persona_id]


def list_persona_ids() -> list[str]:
    return list(_registry.keys())
