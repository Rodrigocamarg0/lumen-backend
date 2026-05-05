"""
FastAPI application entry point.

Startup sequence (lifespan):
  1. Initialize app database tables.
  2. Load FAISS index + chunk metadata from disk.
  3. Validate external LLM provider config.
  4. Wire up the RAGOrchestrator singleton in `app.state`.

If the index or model files are absent the server still starts but the
/api/health endpoint will report `status: "degraded"` or `"error"`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI

from app import state
from app.config import Settings, settings
from app.security import add_security_middleware

logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Paths (override via env / .env if needed)
# ---------------------------------------------------------------------------

INDEX_DIR = Path("data/kardec/index")
INDEX_NAME = "kardec"


def _resolve_embedding_model_for_index(idx, configured_model: str) -> str:
    from app.corpus.embedder import Embedder

    if idx.embedding_model:
        return idx.embedding_model

    configured_embedder = Embedder(model_name=configured_model, cache_dir=None)
    configured_dim = configured_embedder.dim
    if idx.dim == configured_dim:
        return configured_model

    raise RuntimeError(
        f"Loaded index dimension ({idx.dim}) does not match configured embedding model "
        f"'{configured_model}' (dim={configured_dim}). The on-disk index appears stale or was "
        "built with a different embedding model. Re-run ./ingest.sh to rebuild it."
    )


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup ----
    import asyncio

    loop = asyncio.get_event_loop()

    # Load the FAISS index in a thread-pool executor (I/O bound)
    try:
        from app.db.session import init_db

        init_db()
        logger.info("Application database tables ready")
    except Exception as exc:
        logger.error(f"Failed to initialize application database: {exc}")

    try:
        from app.corpus.embedder import Embedder
        from app.corpus.indexer import KardecIndex

        logger.info(f"Loading FAISS index from {INDEX_DIR} …")
        idx = await loop.run_in_executor(
            None,
            lambda: KardecIndex.load(INDEX_DIR, name=INDEX_NAME),
        )
        embedding_model = _resolve_embedding_model_for_index(idx, settings.EMBEDDING_MODEL)
        logger.info(
            f"RAG query embedder model: {embedding_model} "
            f"(index dim={idx.dim}, storage={idx.storage_format})"
        )
        embedder = Embedder(model_name=embedding_model, cache_dir=None)

        from app.persona.rag import RAGOrchestrator

        q_index = None
        try:
            from app.corpus.question_index import QuestionIndex

            # Build question-only embeddings for L.E. chunks (RRF fusion).
            # Optional: if this fails, keep the baseline FAISS RAG path available.
            chunks_dir = INDEX_DIR.parent / "chunks"
            q_embedder = Embedder(model_name=embedding_model)
            q_index = await loop.run_in_executor(
                None,
                lambda: QuestionIndex.build(chunks_dir, q_embedder),
            )
        except Exception as exc:
            logger.warning(f"Question index unavailable; using baseline RAG retrieval: {exc}")

        state.rag = RAGOrchestrator(index=idx, embedder=embedder, question_index=q_index)
        q_index_size = q_index.size if q_index is not None else 0
        logger.info(f"RAG orchestrator ready (question_index: {q_index_size} questions)")
    except FileNotFoundError:
        logger.warning(
            "FAISS index not found — run `python -m app.corpus.parser` and "
            "`python -m app.corpus.indexer` to build it. "
            "The server starts in degraded mode."
        )
    except Exception as exc:
        state.rag = None
        logger.error(f"Failed to load index: {exc}")

    # Build the persona agent registry regardless of RAG status.
    # Agents can still function (without RAG context) in degraded mode.
    try:
        from app.agents.registry import build_registry

        build_registry()
        logger.info("[agents] registry built")
    except Exception as exc:
        logger.error(f"Failed to build agent registry: {exc}")

    # Validate external LLM provider configuration.
    try:
        from app.llm import engine as llm_engine

        llm_engine.load()
    except Exception as exc:
        logger.error(f"Failed to initialize LLM provider: {exc}")

    yield  # ---- Application running ----

    # ---- Shutdown ---- (nothing to clean up for Phase 1)
    logger.info("Shutting down Lumen …")


def create_app(app_settings: Settings = settings) -> FastAPI:
    app_settings.validate_security_config()

    app = FastAPI(
        title="Lumen API",
        description="Lumen — Persona Engine (Kardec Corpus RAG)",
        version="1.0.0",
        lifespan=lifespan,
    )

    add_security_middleware(app, app_settings)

    from app.api.routes import admin, chat, health, me, memories, personas, search, sessions, terms

    app.include_router(admin.router, prefix="/api", tags=["Admin"])
    app.include_router(health.router, prefix="/api", tags=["Health"])
    app.include_router(me.router, prefix="/api", tags=["Auth"])
    app.include_router(terms.router, prefix="/api", tags=["Auth"])
    app.include_router(personas.router, prefix="/api", tags=["Personas"])
    app.include_router(chat.router, prefix="/api", tags=["Chat"])
    app.include_router(search.router, prefix="/api", tags=["Search"])
    app.include_router(sessions.router, prefix="/api", tags=["Sessions"])
    app.include_router(memories.router, prefix="/api", tags=["Memories"])
    return app


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = create_app()

# ---------------------------------------------------------------------------
# Dev server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
