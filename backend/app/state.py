"""
Global application state — holds the loaded RAG orchestrator.

Imported by route handlers; populated during FastAPI lifespan startup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.persona.rag import RAGOrchestrator

rag: RAGOrchestrator | None = None
