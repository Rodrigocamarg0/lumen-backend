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
# Session KV-cache store (in-memory; no persistence needed for Phase 1)
# ---------------------------------------------------------------------------

_sessions: dict[str, dict] = {}


def _get_or_create_session(session_id: str | None) -> str:
    sid = session_id or str(uuid.uuid4())
    if sid not in _sessions:
        _sessions[sid] = {
            "history": [],
            "kv_tokens": 0,
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
        max_new_tokens: int = settings.MAX_NEW_TOKENS,
        top_k_chunks: int = 5,
        temperature: float = 0.7,
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
        system_prompt = build_system_prompt(persona_id, chunks)

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
        session["kv_tokens"] += tokens_generated
        kv_tokens = session["kv_tokens"]
        kv_metrics = engine.kv_cache_metrics()
        kv_mb = float(kv_metrics.get("compressed_mb", 0.0))

        stats = {
            "session_id": sid,
            "tokens_generated": tokens_generated,
            "tokens_per_second": round(tps, 1),
            "kv_cache_tokens": kv_tokens,
            "kv_cache_mb": kv_mb,
            "rag_latency_ms": rag_latency_ms,
            "generation_latency_ms": gen_latency_ms,
        }
        if kv_metrics.get("enabled"):
            stats["kv_cache_compression_ratio"] = kv_metrics.get("compression_ratio", 1.0)
            stats["kv_cache_layers_initialized"] = kv_metrics.get("layers_initialized", 0)
            stats["kv_cache_max_seq_length"] = kv_metrics.get("max_seq_length", 0)
        yield ("stats", stats)
        yield ("done", None)
