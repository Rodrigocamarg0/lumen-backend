"""
Evaluate retrieval recall for O Livro dos Espíritos question chunks.

Default: sample 50 real L.E. question texts from the local chunk file and
compare semantic search against the question-aware reranker.

Run from repo root:
    PYTHONPATH=backend uv run python -m evals.lde_question_recall
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import os
from pathlib import Path
import random

import numpy as np

from app.config import settings
from app.corpus.embedder import Embedder
from app.corpus.indexer import KardecIndex
from app.persona.rag import rerank_question_matches


@dataclass(frozen=True)
class EvalCase:
    query: str
    expected_chunk_id: str
    questao: int | None = None


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


def _question_text(chunk: dict) -> str:
    text = (chunk.get("texto") or "").strip()
    answer_pos = text.find('"')
    if answer_pos >= 0:
        text = text[:answer_pos]
    return " ".join(text.split())


def _load_lde_cases(chunks_path: Path, *, sample_size: int, seed: int) -> list[EvalCase]:
    cases: list[EvalCase] = []
    with chunks_path.open(encoding="utf-8") as file:
        for line in file:
            chunk = json.loads(line)
            if "Livro dos Espíritos" not in (chunk.get("obra") or ""):
                continue
            question = _question_text(chunk)
            if not question:
                continue
            cases.append(
                EvalCase(
                    query=question,
                    expected_chunk_id=chunk["id"],
                    questao=chunk.get("questao"),
                )
            )

    rng = random.Random(seed)
    rng.shuffle(cases)
    return cases[: min(sample_size, len(cases))]


def _load_fixture_cases(fixture_path: Path, *, sample_size: int, seed: int) -> list[EvalCase]:
    rows = json.loads(fixture_path.read_text(encoding="utf-8"))
    cases = [
        EvalCase(query=row["query"], expected_chunk_id=row["expected_chunk_id"]) for row in rows
    ]
    rng = random.Random(seed)
    rng.shuffle(cases)
    return cases[: min(sample_size, len(cases))]


def _rank_of(chunks: list[dict], target_id: str) -> int | None:
    for index, chunk in enumerate(chunks, start=1):
        if chunk.get("id") == target_id:
            return index
    return None


def _bucket(rank: int | None) -> str:
    if rank is None:
        return "miss"
    if rank == 1:
        return "top1"
    if rank <= 3:
        return "top3"
    if rank <= 5:
        return "top5"
    if rank <= 10:
        return "top10"
    if rank <= 20:
        return "top20"
    if rank <= 50:
        return "top50"
    if rank <= 100:
        return "top100"
    return "over100"


def _recall(ranks: list[int | None], k: int) -> float:
    hits = sum(1 for rank in ranks if rank is not None and rank <= k)
    return round(hits / max(len(ranks), 1), 4)


def _mean_rank(ranks: list[int | None]) -> float | None:
    hits = [rank for rank in ranks if rank is not None]
    if not hits:
        return None
    return round(sum(hits) / len(hits), 2)


def _percentile_rank(ranks: list[int | None], percentile: float) -> int | None:
    hits = sorted(rank for rank in ranks if rank is not None)
    if not hits:
        return None
    index = min(round((len(hits) - 1) * percentile), len(hits) - 1)
    return hits[index]


def _evaluate_case(
    index: KardecIndex,
    query_vec: np.ndarray,
    case: EvalCase,
    *,
    top_k: int,
    candidate_k: int,
    broad_k: int,
) -> dict:
    semantic_broad = index.search(query_vec, top_k=broad_k)
    semantic_rank = _rank_of(semantic_broad, case.expected_chunk_id)
    reranked = rerank_question_matches(
        case.query,
        semantic_broad[:candidate_k],
        top_k=top_k,
    )
    rerank_rank = _rank_of(reranked, case.expected_chunk_id)
    return {
        "query": case.query,
        "expected_chunk_id": case.expected_chunk_id,
        "questao": case.questao,
        "semantic_rank": semantic_rank,
        "rerank_rank": rerank_rank,
        "semantic_top_result": semantic_broad[0].get("id") if semantic_broad else None,
        "rerank_top_result": reranked[0].get("id") if reranked else None,
    }


def main() -> int:
    _load_backend_env()
    parser = argparse.ArgumentParser(description="Evaluate L.E. question retrieval recall.")
    parser.add_argument("--sample-size", type=int, default=50)
    parser.add_argument("--seed", type=int, default=258)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--candidate-k", type=int, default=50)
    parser.add_argument("--broad-k", type=int, default=120)
    parser.add_argument("--index-dir", default="backend/data/kardec/index")
    parser.add_argument("--chunks", default="backend/data/kardec/chunks/lde_chunks.jsonl")
    parser.add_argument("--fixture", help="Optional JSON fixture with query/expected_chunk_id rows")
    parser.add_argument("--show-misses", type=int, default=10)
    args = parser.parse_args()

    if args.fixture:
        cases = _load_fixture_cases(
            Path(args.fixture), sample_size=args.sample_size, seed=args.seed
        )
        mode = "fixture"
    else:
        cases = _load_lde_cases(Path(args.chunks), sample_size=args.sample_size, seed=args.seed)
        mode = "sampled_actual_questions"

    index = KardecIndex.load(Path(args.index_dir), name="kardec")
    embedder = Embedder(model_name=settings.EMBEDDING_MODEL)
    vectors = embedder.encode([case.query for case in cases])

    rows = [
        _evaluate_case(
            index,
            np.atleast_2d(vectors[idx]),
            case,
            top_k=args.top_k,
            candidate_k=args.candidate_k,
            broad_k=args.broad_k,
        )
        for idx, case in enumerate(cases)
    ]

    semantic_ranks = [row["semantic_rank"] for row in rows]
    rerank_ranks = [row["rerank_rank"] for row in rows]
    summary = {
        "mode": mode,
        "sample_size": len(cases),
        "seed": args.seed,
        "top_k": args.top_k,
        "candidate_k": args.candidate_k,
        "broad_k": args.broad_k,
        "semantic": {
            "recall_at_1": _recall(semantic_ranks, 1),
            "recall_at_3": _recall(semantic_ranks, 3),
            "recall_at_10": _recall(semantic_ranks, 10),
            "recall_at_20": _recall(semantic_ranks, 20),
            "recall_at_50": _recall(semantic_ranks, 50),
            "recall_at_100": _recall(semantic_ranks, 100),
            "mean_hit_rank": _mean_rank(semantic_ranks),
            "p90_hit_rank": _percentile_rank(semantic_ranks, 0.9),
            "rank_buckets": dict(Counter(_bucket(rank) for rank in semantic_ranks)),
        },
        "reranked": {
            "recall_at_10": _recall(rerank_ranks, args.top_k),
            "mean_hit_rank": _mean_rank(rerank_ranks),
            "p90_hit_rank": _percentile_rank(rerank_ranks, 0.9),
            "rank_buckets": dict(Counter(_bucket(rank) for rank in rerank_ranks)),
        },
        "misses_or_needs_broad_candidates": [
            row
            for row in rows
            if row["rerank_rank"] is None
            or (row["semantic_rank"] or args.broad_k + 1) > args.candidate_k
        ][: args.show_misses],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["reranked"]["recall_at_10"] >= 0.9 else 1


if __name__ == "__main__":
    raise SystemExit(main())
