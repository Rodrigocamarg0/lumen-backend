"""
Experiment: question-only embeddings for L.E. chunks.

For LDE chunks (Q&A format), this creates a separate FAISS index
over just the question text. At retrieval time, we search both the
full-text index and the question-only index, then merge results
using reciprocal rank fusion.

Run from repo root:
    PYTHONPATH=backend python -m evals.exp_question_embeddings
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import time

import numpy as np

from app.config import settings
from app.corpus.embedder import Embedder
from app.corpus.indexer import KardecIndex
from app.persona.rag import rerank_question_matches
from evals.retrieval_eval import (
    _bucket,
    _first_hit_rank,
    load_gold,
    mrr,
    ndcg_at_k,
    recall_at_k,
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


def _extract_question_text(chunk: dict) -> str:
    """Extract just the question portion of an L.E. chunk."""
    if not chunk.get("questao"):
        return ""
    text = (chunk.get("texto") or "").strip()
    answer_pos = text.find('"')
    if answer_pos >= 0:
        text = text[:answer_pos]
    return text.strip()


def _build_question_index(chunks_path: Path, embedder: Embedder) -> tuple[list[dict], np.ndarray]:
    """Build question-only embeddings for LDE chunks."""
    question_chunks: list[dict] = []
    question_texts: list[str] = []

    with chunks_path.open(encoding="utf-8") as fh:
        for line in fh:
            chunk = json.loads(line)
            q_text = _extract_question_text(chunk)
            if q_text and len(q_text) >= 10:
                question_chunks.append(chunk)
                question_texts.append(q_text)

    print(f"Embedding {len(question_texts)} question-only texts...")
    t0 = time.perf_counter()
    vectors = embedder.encode(question_texts)
    print(f"Question embeddings done in {time.perf_counter() - t0:.1f}s")

    return question_chunks, vectors


def _search_question_index(
    query_vec: np.ndarray,
    q_chunks: list[dict],
    q_vectors: np.ndarray,
    top_k: int,
) -> list[dict]:
    """Search the question-only vectors using numpy dot product."""
    qv = np.atleast_2d(query_vec).astype(np.float32)
    scores = (q_vectors @ qv.T).flatten()
    top_indices = scores.argsort()[::-1][:top_k]

    results: list[dict] = []
    for idx in top_indices:
        chunk = dict(q_chunks[idx])
        chunk["score"] = round(float(scores[idx]), 6)
        chunk["q_only_score"] = round(float(scores[idx]), 6)
        results.append(chunk)
    return results


def _reciprocal_rank_fusion(list_a: list[dict], list_b: list[dict], k: int = 60) -> list[dict]:
    scores: dict[str, float] = {}
    chunk_map: dict[str, dict] = {}
    for rank, c in enumerate(list_a, 1):
        cid = c.get("id", "")
        scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank)
        chunk_map[cid] = c
    for rank, c in enumerate(list_b, 1):
        cid = c.get("id", "")
        scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank)
        if cid not in chunk_map:
            chunk_map[cid] = c
    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
    return [dict(chunk_map[cid], rrf_score=round(scores[cid], 6)) for cid in sorted_ids]


def _compute_metrics(rows: list[dict], key: str) -> dict:
    ranks = [r[key] for r in rows]
    return {
        "count": len(ranks),
        "recall@1": recall_at_k(ranks, 1),
        "recall@3": recall_at_k(ranks, 3),
        "recall@5": recall_at_k(ranks, 5),
        "recall@10": recall_at_k(ranks, 10),
        "mrr": mrr(ranks),
        "ndcg@10": ndcg_at_k(ranks, 10),
        "buckets": dict(Counter(_bucket(r) for r in ranks)),
    }


def main() -> int:
    _load_backend_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", default="evals/data/gold_retrieval_300.json")
    parser.add_argument("--index-dir", default="backend/data/kardec/index")
    parser.add_argument("--lde-chunks", default="backend/data/kardec/chunks/lde_chunks.jsonl")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--broad-k", type=int, default=120)
    parser.add_argument("--candidate-k", type=int, default=50)
    parser.add_argument("--show-misses", type=int, default=10)
    parser.add_argument("--output", default="evals/results/exp_question_embeddings.json")
    args = parser.parse_args()

    entries = load_gold(Path(args.gold))
    print(f"Loaded {len(entries)} gold entries")

    # Load main index + embedder
    index = KardecIndex.load(Path(args.index_dir), name="kardec")
    embedder = Embedder(model_name=settings.EMBEDDING_MODEL)

    # Build question-only index
    q_chunks, q_vectors = _build_question_index(Path(args.lde_chunks), embedder)
    # L2 normalize for cosine sim
    norms = np.linalg.norm(q_vectors, axis=1, keepdims=True)
    q_vectors = (q_vectors / np.where(norms > 0, norms, 1.0)).astype(np.float32)

    # Encode queries
    t0 = time.perf_counter()
    query_vectors = embedder.encode([e.query for e in entries])
    print(f"Encoded {len(entries)} queries in {time.perf_counter() - t0:.1f}s")

    # Evaluate
    rows: list[dict] = []
    for i, entry in enumerate(entries):
        qv = np.atleast_2d(query_vectors[i])
        expected = set(entry.expected_ids)

        # Full-text semantic
        semantic_results = index.search(qv, top_k=args.broad_k)
        semantic_ids = [c.get("id", "") for c in semantic_results]
        semantic_rank = _first_hit_rank(semantic_ids, expected)

        # Question-only
        q_results = _search_question_index(qv, q_chunks, q_vectors, top_k=args.broad_k)

        # RRF merge: full-text + question-only
        fused = _reciprocal_rank_fusion(semantic_results, q_results)
        fused_ids = [c.get("id", "") for c in fused]
        fused_rank = _first_hit_rank(fused_ids, expected)

        # Fused + question rerank
        reranked = rerank_question_matches(entry.query, fused[: args.candidate_k], top_k=args.top_k)
        reranked_ids = [c.get("id", "") for c in reranked]
        reranked_rank = _first_hit_rank(reranked_ids, expected)

        rows.append(
            {
                "query": entry.query,
                "expected_ids": entry.expected_ids,
                "type": entry.query_type,
                "source_book": entry.source_book,
                "semantic_rank": semantic_rank,
                "fused_rank": fused_rank,
                "reranked_rank": reranked_rank,
                "reranked_top3": reranked_ids[:3],
            }
        )

    # Summary
    summary = {
        "experiment": "question_only_embeddings_rrf",
        "total_entries": len(rows),
        "overall_semantic": _compute_metrics(rows, "semantic_rank"),
        "overall_fused": _compute_metrics(rows, "fused_rank"),
        "overall_fused_reranked": _compute_metrics(rows, "reranked_rank"),
    }
    summary["by_type"] = {}
    for qtype in ("exact_question", "near_paraphrase", "conceptual_query"):
        subset = [r for r in rows if r["type"] == qtype]
        if subset:
            summary["by_type"][qtype] = {
                "semantic": _compute_metrics(subset, "semantic_rank"),
                "fused": _compute_metrics(subset, "fused_rank"),
                "fused_reranked": _compute_metrics(subset, "reranked_rank"),
            }

    misses = [r for r in rows if r["reranked_rank"] is None]
    summary["miss_count"] = len(misses)
    summary["misses"] = misses[: args.show_misses]

    # Print table
    print("\n" + "=" * 80)
    print(
        f"{'Strategy':<30} {'R@1':>6} {'R@3':>6} {'R@5':>6} {'R@10':>6} {'MRR':>6} {'NDCG@10':>8}"
    )
    print("-" * 80)
    for label, key in [
        ("Semantic baseline", "overall_semantic"),
        ("Fused (full+Q-only)", "overall_fused"),
        ("Fused + Q-rerank", "overall_fused_reranked"),
    ]:
        m = summary[key]
        print(
            f"{label:<30} {m['recall@1']:>6.2f} {m['recall@3']:>6.2f} {m['recall@5']:>6.2f} {m['recall@10']:>6.2f} {m['mrr']:>6.2f} {m['ndcg@10']:>8.2f}"
        )

    print("\n--- By query type (fused + reranked) ---")
    for qtype, data in summary["by_type"].items():
        m = data["fused_reranked"]
        print(f"  {qtype:<22} R@10={m['recall@10']:.2f}  MRR={m['mrr']:.2f}  n={m['count']}")

    print(f"\nTotal misses: {summary['miss_count']}")
    for miss in misses[: args.show_misses]:
        print(f"  query: {miss['query'][:80]}")
        print(f"    expected: {miss['expected_ids']}")
        print(f"    got top3: {miss['reranked_top3']}")
        print()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(f"Results saved to {args.output}")

    return 0 if summary["overall_fused_reranked"]["recall@10"] >= 0.8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
