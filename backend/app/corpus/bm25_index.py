"""
BM25 lexical index for hybrid retrieval.

Builds a BM25 index over all corpus chunks at startup, enabling hybrid
(semantic + lexical) retrieval that improves recall for exact doctrinal
terms and paraphrased questions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import unicodedata

from rank_bm25 import BM25Okapi

logger = logging.getLogger("bm25")

_TOKEN_RE = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)
_STOPWORDS = {
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
    "é",
    "não",
    "mais",
    "como",
    "mas",
    "ou",
    "para",
    "seu",
    "sua",
    "seus",
    "suas",
    "ele",
    "ela",
    "eles",
    "elas",
    "isso",
    "isto",
    "esta",
    "este",
    "essa",
    "esse",
}


def _normalize(token: str) -> str:
    decomposed = unicodedata.normalize("NFKD", token.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def tokenize(text: str) -> list[str]:
    return [
        tok
        for raw in _TOKEN_RE.findall(text)
        if len(tok := _normalize(raw)) > 2 and tok not in _STOPWORDS
    ]


class BM25Index:
    """In-memory BM25 index over all corpus chunks."""

    def __init__(self, chunks: list[dict], corpus_tokens: list[list[str]]):
        self._chunks = chunks
        self._bm25 = BM25Okapi(corpus_tokens)

    @classmethod
    def from_chunks_dir(cls, chunks_dir: Path) -> BM25Index:
        chunks: list[dict] = []
        for jsonl_path in sorted(chunks_dir.glob("*.jsonl")):
            with jsonl_path.open(encoding="utf-8") as fh:
                for line in fh:
                    chunks.append(json.loads(line))

        corpus_tokens = [tokenize(c.get("texto", "")) for c in chunks]
        logger.info(f"BM25 index built: {len(chunks)} chunks")
        return cls(chunks, corpus_tokens)

    def search(self, query: str, top_k: int = 50) -> list[dict]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)
        top_indices = scores.argsort()[::-1][:top_k]

        results: list[dict] = []
        for idx in top_indices:
            score = float(scores[idx])
            if score <= 0:
                break
            chunk = dict(self._chunks[idx])
            chunk["bm25_score"] = round(score, 6)
            results.append(chunk)
        return results
