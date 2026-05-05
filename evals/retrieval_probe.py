"""
Inspect local RAG retrieval for one prompt.

Run from repo root:
    PYTHONPATH=backend uv run python -m evals.retrieval_probe
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.config import settings
from app.corpus.embedder import Embedder
from app.corpus.indexer import KardecIndex
from app.persona.rag import RAGOrchestrator

DEFAULT_QUERY = (
    "No estado errante, antes de nova existência corpórea, o Espírito tem consciência "
    "e previsão do que lhe vai acontecer durante a vida?"
)


def _load_backend_env() -> None:
    env_path = Path("backend/.env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    _load_backend_env()
    parser = argparse.ArgumentParser(description="Probe local RAG retrieval results.")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--target-id", default="lde-q0258")
    parser.add_argument("--index-dir", default="backend/data/kardec/index")
    args = parser.parse_args()

    index = KardecIndex.load(Path(args.index_dir), name="kardec")
    embedder = Embedder(model_name=settings.EMBEDDING_MODEL, cache_dir=None)
    rag = RAGOrchestrator(index=index, embedder=embedder)
    chunks, latency_ms = rag.retrieve(args.query, top_k=args.top_k)

    rows = []
    for rank, chunk in enumerate(chunks, start=1):
        rows.append(
            {
                "rank": rank,
                "id": chunk.get("id"),
                "questao": chunk.get("questao"),
                "score": chunk.get("score"),
                "semantic_score": chunk.get("semantic_score"),
                "question_match_score": chunk.get("question_match_score"),
                "excerpt": (chunk.get("texto") or "").replace("\n", " ")[:300],
            }
        )

    target_rank = next((row["rank"] for row in rows if row["id"] == args.target_id), None)
    summary = {
        "query": args.query,
        "target_id": args.target_id,
        "target_rank": target_rank,
        "latency_ms": latency_ms,
        "results": rows,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if target_rank is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
