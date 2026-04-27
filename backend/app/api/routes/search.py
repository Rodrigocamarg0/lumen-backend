"""
POST /api/search — direct semantic corpus search (no LLM generation).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app import state
from app.agents.registry import list_persona_ids
from app.api.models import SearchRequest, SearchResponse, SearchResult
from app.auth.dependencies import require_current_user
from app.auth.models import AuthenticatedUser
from app.persona.rag import make_citation_label

logger = logging.getLogger("routes.search")
router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search_endpoint(
    request: SearchRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
):
    persona_ids = list_persona_ids()
    if request.persona_id not in persona_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Persona '{request.persona_id}' not found. Available: {persona_ids}",
        )

    if state.rag is None:
        raise HTTPException(
            status_code=503,
            detail="Index not loaded — run the ingestion pipeline first.",
        )

    chunks, latency_ms = state.rag.retrieve(
        query=request.query,
        top_k=request.top_k,
        min_score=request.min_score,
    )

    results = [
        SearchResult(
            id=c.get("id", ""),
            obra=c.get("obra", ""),
            parte=c.get("parte"),
            capitulo=c.get("capitulo"),
            questao=c.get("questao"),
            label=make_citation_label(c),
            score=round(float(c.get("score", 0.0)), 4),
            excerpt=(c.get("texto") or "")[:300],
            texto="",
        )
        for c in chunks
    ]

    return SearchResponse(
        query=request.query,
        results=results,
        latency_ms=latency_ms,
        index_size=state.rag.index.size,
    )
