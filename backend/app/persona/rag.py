"""
RAG orchestrator: User Query → FAISS Search → Context Formatting →
System Prompt → LLM Generation (streaming).

The orchestrator holds references to:
  - a KardecIndex (FAISS wrapper)
  - an Embedder (OpenAI text-embedding-3-small)
  - the LLM engine module (app.llm.engine)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
import logging
import time
import uuid

from app.config import settings
from app.corpus.embedder import Embedder
from app.corpus.indexer import KardecIndex
from app.persona.prompts import build_system_prompt, get_few_shot_examples

logger = logging.getLogger("rag")


def _engine():
    """Lazy import so the module is importable without a loaded model."""
    from app.llm import engine

    return engine


# ---------------------------------------------------------------------------
# Citation label helper
# ---------------------------------------------------------------------------


def make_citation_label(chunk: dict) -> str:
    obra = chunk.get("obra", "")
    questao = chunk.get("questao")
    capitulo = chunk.get("capitulo") or ""
    if "Espíritos" in obra and questao:
        return f"L.E. Q.{questao}"
    if "Médiuns" in obra:
        return f"L.M. Art.{questao or chunk.get('id', '')}"
    if "Evangelho" in obra:
        return f"Ev. {capitulo[:30]}" if capitulo else f"Ev. {chunk.get('id', '')}"
    if "Céu" in obra:
        return f"C.I. {chunk.get('id', '')}"
    if "Gênese" in obra:
        return f"Gên. {capitulo[:30]}" if capitulo else f"Gên. {chunk.get('id', '')}"
    return chunk.get("id", "ref.")


def chunk_to_citation(chunk: dict) -> dict:
    return {
        "id": chunk.get("id", ""),
        "obra": chunk.get("obra", ""),
        "parte": chunk.get("parte"),
        "capitulo": chunk.get("capitulo"),
        "questao": chunk.get("questao"),
        "label": make_citation_label(chunk),
        "score": round(float(chunk.get("score", 0.0)), 4),
        "excerpt": (chunk.get("texto") or "")[:200],
    }


# ---------------------------------------------------------------------------
# Lightweight stream accounting
# ---------------------------------------------------------------------------

_sessions: dict[str, dict] = {}


def _get_or_create_session(session_id: str | None) -> str:
    sid = session_id or str(uuid.uuid4())
    if sid not in _sessions:
        _sessions[sid] = {
            "history": [],
            "tokens_generated": 0,
            "last_active": time.time(),
        }
    else:
        _sessions[sid]["last_active"] = time.time()
    return sid


# ---------------------------------------------------------------------------
# RAG Orchestrator
# ---------------------------------------------------------------------------


class RAGOrchestrator:
    """
    Stateless orchestrator (state lives in the module-level _sessions dict
    and in the passed-in index/embedder singletons).
    """

    def __init__(self, index: KardecIndex, embedder: Embedder):
        self.index = index
        self.embedder = embedder

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> tuple[list[dict], int]:
        """
        Returns (chunks_with_score, latency_ms).
        """
        t0 = time.perf_counter()
        q_vec = self.embedder.encode_query(query)
        t_embed = time.perf_counter()
        chunks = self.index.search(q_vec, top_k=top_k, min_score=min_score)
        t_search = time.perf_counter()
        embed_ms = int((t_embed - t0) * 1000)
        search_ms = int((t_search - t_embed) * 1000)
        latency_ms = int((t_search - t0) * 1000)
        logger.debug(
            f"RAG embed={embed_ms}ms  search={search_ms}ms  total={latency_ms}ms  chunks={len(chunks)}"
        )
        return chunks, latency_ms

    # ------------------------------------------------------------------
    # Streaming generation
    # ------------------------------------------------------------------

    async def astream_response(
        self,
        persona_id: str,
        message: str,
        session_id: str | None,
        history: list[dict],
        session_summary: str | None = None,
        user_memories: list[str] | None = None,
        session_state: dict | None = None,
        max_new_tokens: int = settings.MAX_NEW_TOKENS,
        top_k_chunks: int = 5,
        temperature: float = 0.7,
        reasoning_effort: str = "off",
    ) -> AsyncIterator[tuple[str, object]]:  # (event_type, payload)
        """
        Async generator that yields (event_type, payload) tuples:

          ("token",     "some token string")
          ("citations", [citation_dict, ...])
          ("stats",     {stats_dict})
          ("done",      None)
          ("error",     "error detail string")
        """
        sid = _get_or_create_session(session_id)
        session = _sessions[sid]

        # 1. Retrieve context
        try:
            chunks, rag_latency_ms = self.retrieve(message, top_k=top_k_chunks)
        except Exception as exc:
            logger.exception("RAG retrieval failed")
            yield ("error", f"Retrieval failed: {exc}")
            return

        # 2. Build system prompt with context
        system_prompt = build_system_prompt(
            persona_id,
            chunks,
            session_summary=session_summary,
            user_memories=user_memories,
            session_state=session_state,
        )

        # 3. Merge few-shot examples into history (prepend to passed history)
        few_shot = get_few_shot_examples(persona_id)
        full_history = few_shot + list(history)

        # 4. Stream tokens
        engine = _engine()
        if not engine.is_loaded():
            yield (
                "error",
                "Model not loaded — try again after /api/health reports model_loaded=true",
            )
            return

        tokens_generated = 0
        t_gen_start = time.perf_counter()
        try:
            async for token in engine.astream_tokens(
                system_prompt=system_prompt,
                history=full_history,
                user_message=message,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
            ):
                tokens_generated += 1
                yield ("token", token)
        except Exception as exc:
            logger.exception("Generation failed")
            yield ("error", f"Generation failed: {exc}")
            return

        t_gen_end = time.perf_counter()
        gen_latency_ms = int((t_gen_end - t_gen_start) * 1000)
        tps = tokens_generated / max((t_gen_end - t_gen_start), 0.001)

        # 5. Citations
        citations = [chunk_to_citation(c) for c in chunks]
        yield ("citations", citations)

        # 6. Stats
        session["tokens_generated"] += tokens_generated
        stats = {
            "session_id": sid,
            "tokens_generated": tokens_generated,
            "tokens_per_second": round(tps, 1),
            "rag_latency_ms": rag_latency_ms,
            "generation_latency_ms": gen_latency_ms,
        }
        yield ("stats", stats)
        yield ("done", None)
