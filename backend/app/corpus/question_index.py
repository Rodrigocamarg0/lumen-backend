"""
Question-only embedding index for L.E. chunks.

L.E. chunks embed the full question+answer together, which dilutes the
question signal when the answer text is long. This module creates a
separate in-memory index over just the question portions, enabling
RRF-fused retrieval that dramatically improves paraphrase recall.

Lifecycle:
    q_idx = QuestionIndex.build(chunks_dir, embedder)  # at startup
    results = q_idx.search(query_vec, top_k=120)       # at query time
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import time

import numpy as np

logger = logging.getLogger("question_index")


def _extract_question_text(chunk: dict) -> str:
    """Extract just the question portion of an L.E. chunk (before the answer)."""
    if not chunk.get("questao"):
        return ""
    text = (chunk.get("texto") or "").strip()
    answer_pos = text.find('"')
    if answer_pos >= 0:
        text = text[:answer_pos]
    return text.strip()


class QuestionIndex:
    """In-memory cosine-similarity index over L.E. question-only embeddings."""

    def __init__(self, chunks: list[dict], vectors: np.ndarray):
        self._chunks = chunks
        self._vectors = vectors  # (N, dim), L2-normalised

    @classmethod
    def build(cls, chunks_dir: Path, embedder) -> QuestionIndex:
        """Build question-only embeddings for all LDE chunks with questions."""
        question_chunks: list[dict] = []
        question_texts: list[str] = []

        lde_path = chunks_dir / "lde_chunks.jsonl"
        if not lde_path.exists():
            logger.warning(f"LDE chunks not found at {lde_path}; QuestionIndex will be empty")
            return cls([], np.empty((0, 0), dtype=np.float32))

        with lde_path.open(encoding="utf-8") as fh:
            for line in fh:
                chunk = json.loads(line)
                q_text = _extract_question_text(chunk)
                if q_text and len(q_text) >= 10:
                    question_chunks.append(chunk)
                    question_texts.append(q_text)

        if not question_texts:
            logger.warning("No question texts found in LDE chunks")
            return cls([], np.empty((0, 0), dtype=np.float32))

        t0 = time.perf_counter()
        vectors = embedder.encode(question_texts)
        elapsed = time.perf_counter() - t0

        # L2-normalise for cosine similarity via dot product
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        vectors = (vectors / np.where(norms > 0, norms, 1.0)).astype(np.float32)

        logger.info(
            f"QuestionIndex built: {len(question_chunks)} questions, {elapsed:.1f}s embedding time"
        )
        return cls(question_chunks, vectors)

    @property
    def size(self) -> int:
        return len(self._chunks)

    def is_ready(self) -> bool:
        return len(self._chunks) > 0

    def search(self, query_vec: np.ndarray, top_k: int = 120) -> list[dict]:
        """Search question-only embeddings by cosine similarity (dot product)."""
        if not self._chunks:
            return []

        qv = np.atleast_2d(query_vec).astype(np.float32)
        scores = (self._vectors @ qv.T).flatten()
        top_indices = scores.argsort()[::-1][:top_k]

        results: list[dict] = []
        for idx in top_indices:
            if float(scores[idx]) <= 0:
                break
            chunk = dict(self._chunks[idx])
            chunk["score"] = round(float(scores[idx]), 6)
            results.append(chunk)
        return results
