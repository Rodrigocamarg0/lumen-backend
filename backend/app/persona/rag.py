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
import re
import time
import unicodedata
import uuid

from app.config import settings
from app.corpus.embedder import Embedder
from app.corpus.indexer import KardecIndex
from app.persona.prompts import build_system_prompt, get_few_shot_examples

logger = logging.getLogger("rag")

_MIN_RERANK_CANDIDATES = 50
_MAX_RERANK_CANDIDATES = 120
_QUESTION_BOOST_WEIGHT = 0.16
_QUESTION_TEXT_LIMIT = 500
_TOKEN_RE = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)
_QUESTION_STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "por",
    "que",
    "se",
    "tem",
    "um",
    "uma",
}


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


def _normalize_token(token: str) -> str:
    decomposed = unicodedata.normalize("NFKD", token.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for raw_token in _TOKEN_RE.findall(text)
        if len(token := _normalize_token(raw_token)) > 2 and token not in _QUESTION_STOPWORDS
    }


def _chunk_question_text(chunk: dict) -> str:
    if not chunk.get("questao"):
        return ""
    text = (chunk.get("texto") or "").strip()
    if not text:
        return ""
    answer_pos = text.find('"')
    if answer_pos >= 0:
        text = text[:answer_pos]
    return text[:_QUESTION_TEXT_LIMIT].strip()


def question_similarity(query: str, chunk: dict) -> float:
    """
    Lightweight lexical similarity between the user prompt and the chunk's
    leading question. This complements embedding search when the user asks a
    paraphrase of a canonical L.E. question whose answer text dilutes the chunk
    embedding.
    """
    query_tokens = _content_tokens(query)
    question_tokens = _content_tokens(_chunk_question_text(chunk))
    if not query_tokens or not question_tokens:
        return 0.0
    overlap = query_tokens & question_tokens
    containment = len(overlap) / min(len(query_tokens), len(question_tokens))
    jaccard = len(overlap) / len(query_tokens | question_tokens)
    return round((0.7 * containment) + (0.3 * jaccard), 6)


def rerank_question_matches(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    reranked: list[dict] = []
    for index, chunk in enumerate(chunks):
        item = dict(chunk)
        semantic_score = float(item.get("score", 0.0))
        question_score = question_similarity(query, item)
        item["semantic_score"] = round(semantic_score, 6)
        item["question_match_score"] = question_score
        item["score"] = round(semantic_score + (_QUESTION_BOOST_WEIGHT * question_score), 6)
        item["_retrieval_rank"] = index
        reranked.append(item)

    reranked.sort(
        key=lambda item: (float(item["score"]), -int(item["_retrieval_rank"])), reverse=True
    )
    for item in reranked:
        item.pop("_retrieval_rank", None)
    return reranked[:top_k]


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
        candidate_k = min(max(top_k * 5, _MIN_RERANK_CANDIDATES), _MAX_RERANK_CANDIDATES)
        chunks = self.index.search(q_vec, top_k=candidate_k, min_score=min_score)
        chunks = rerank_question_matches(query, chunks, top_k=top_k)
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
        top_k_chunks: int = 10,
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
