"""
FastAPI application entry point.

Startup sequence (lifespan):
  1. Load FAISS index + chunk metadata from disk.
  2. Load Gemma 4 E4B (4-bit) into GPU memory.
  3. Wire up the RAGOrchestrator singleton in `app.state`.

If the index or model files are absent the server still starts but the
/api/health endpoint will report `status: "degraded"` or `"error"`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import state
from app.api.routes import chat, health, search
from app.config import settings

logger = logging.getLogger("main")

# ---------------------------------------------------------------------------
# Paths (override via env / .env if needed)
# ---------------------------------------------------------------------------

INDEX_DIR = Path("data/kardec/index")
INDEX_NAME = "kardec"


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
        from app.corpus.embedder import Embedder
        from app.corpus.indexer import KardecIndex

        logger.info(f"Loading FAISS index from {INDEX_DIR} …")
        idx = await loop.run_in_executor(
            None,
            lambda: KardecIndex.load(INDEX_DIR, name=INDEX_NAME),
        )
        embedder = Embedder(model_name=settings.EMBEDDING_MODEL)

        from app.persona.rag import RAGOrchestrator

        state.rag = RAGOrchestrator(index=idx, embedder=embedder)
        logger.info("RAG orchestrator ready")
    except FileNotFoundError:
        logger.warning(
            "FAISS index not found — run `python -m app.corpus.parser` and "
            "`python -m app.corpus.indexer` to build it. "
            "The server starts in degraded mode."
        )
    except Exception as exc:
        logger.error(f"Failed to load index: {exc}")

    # Load LLM (CPU/GPU bound — done in executor to avoid blocking startup)
    try:
        from app.llm import engine as llm_engine

        logger.info(f"Loading LLM: {settings.MODEL_ID} …")
        await loop.run_in_executor(None, lambda: llm_engine.load(settings.MODEL_ID))
    except Exception as exc:
        logger.error(f"Failed to load LLM: {exc}")

    yield  # ---- Application running ----

    # ---- Shutdown ---- (nothing to clean up for Phase 1)
    logger.info("Shutting down Lumen …")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Lumen API",
    description="Lumen — Persona Engine (Kardec Corpus RAG)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(chat.router, prefix="/api", tags=["Chat"])
app.include_router(search.router, prefix="/api", tags=["Search"])

# ---------------------------------------------------------------------------
# Dev server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
