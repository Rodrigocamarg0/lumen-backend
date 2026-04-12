"""
POST /api/search — direct semantic corpus search (no LLM generation).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app import state
from app.api.models import SearchRequest, SearchResponse, SearchResult
from app.persona.rag import make_citation_label

logger = logging.getLogger("routes.search")
router = APIRouter()

_VALID_PERSONAS = {"kardec"}


@router.post("/search", response_model=SearchResponse)
async def search_endpoint(request: SearchRequest):
    if request.persona_id not in _VALID_PERSONAS:
        raise HTTPException(
            status_code=404,
            detail=f"Persona '{request.persona_id}' not found. Available: {sorted(_VALID_PERSONAS)}",
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
            excerpt=(c.get("texto") or "")[:200],
            texto=c.get("texto", ""),
        )
        for c in chunks
    ]

    return SearchResponse(
        query=request.query,
        results=results,
        latency_ms=latency_ms,
        index_size=state.rag.index.size,
    )
