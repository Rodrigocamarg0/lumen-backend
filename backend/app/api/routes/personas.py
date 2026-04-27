from __future__ import annotations

from fastapi import APIRouter

from app.agents.registry import list_persona_ids
from app.api.models import PersonaResponse
from app.persona.catalog import PERSONA_CATALOG

router = APIRouter()


@router.get("/personas", response_model=list[PersonaResponse])
async def list_personas() -> list[PersonaResponse]:
    enabled_ids = set(list_persona_ids())
    return [
        PersonaResponse(
            id=persona.id,
            name=persona.name,
            subtitle=persona.subtitle,
            description=persona.description,
        )
        for persona in PERSONA_CATALOG
        if persona.id in enabled_ids
    ]
