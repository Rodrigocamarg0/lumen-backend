"""
Retrieval evaluation harness for the gold dataset.

Step 2 of data-science-improvements.md:
  - Recall@K, MRR, NDCG@10, miss analysis
  - Breakdown by query type and source book
  - Compares semantic baseline vs question-reranked

Run from repo root:
    PYTHONPATH=backend python -m evals.retrieval_eval
    PYTHONPATH=backend python -m evals.retrieval_eval --show-misses 20
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import time

import numpy as np

from app.config import settings
from app.corpus.bm25_index import BM25Index
from app.corpus.embedder import Embedder
from app.corpus.indexer import KardecIndex
from app.persona.rag import rerank_question_matches

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldEntry:
    query: str
    expected_ids: list[str]
    query_type: str
    source_book: str
    notes: str


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------


def _first_hit_rank(result_ids: list[str], expected: set[str]) -> int | None:
    """Rank (1-indexed) of the first matching result, or None if miss."""
    for i, rid in enumerate(result_ids, 1):
        if rid in expected:
            return i
    return None


def recall_at_k(ranks: list[int | None], k: int) -> float:
    hits = sum(1 for r in ranks if r is not None and r <= k)
    return round(hits / max(len(ranks), 1), 4)


def mrr(ranks: list[int | None]) -> float:
    rrs = [1.0 / r for r in ranks if r is not None]
    return round(sum(rrs) / max(len(ranks), 1), 4)


def ndcg_at_k(ranks: list[int | None], k: int) -> float:
    """Binary relevance NDCG — 1 if hit in top K, 0 otherwise."""
    dcg_vals: list[float] = []
    for r in ranks:
        if r is not None and r <= k:
            dcg_vals.append(1.0 / math.log2(r + 1))
        else:
            dcg_vals.append(0.0)
    # Ideal DCG: one relevant doc at rank 1
    idcg = 1.0 / math.log2(2)
    return round(sum(dcg_vals) / (max(len(ranks), 1) * idcg), 4)


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
    return "over20"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


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


def load_gold(path: Path) -> list[GoldEntry]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for row in data:
        entries.append(
            GoldEntry(
                query=row["query"],
                expected_ids=row["expected_ids"],
                query_type=row["type"],
                source_book=row.get("source_book", "lde"),
                notes=row.get("notes", ""),
            )
        )
    return entries


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate_entry(
    index: KardecIndex,
    query_vec: np.ndarray,
    entry: GoldEntry,
    *,
    broad_k: int,
    candidate_k: int,
    top_k: int,
) -> dict:
    expected = set(entry.expected_ids)

    # Semantic baseline
    semantic_results = index.search(query_vec, top_k=broad_k)
    semantic_ids = [c.get("id", "") for c in semantic_results]
    semantic_rank = _first_hit_rank(semantic_ids, expected)

    # Question-reranked
    reranked = rerank_question_matches(
        entry.query,
        semantic_results[:candidate_k],
        top_k=top_k,
    )
    reranked_ids = [c.get("id", "") for c in reranked]
    reranked_rank = _first_hit_rank(reranked_ids, expected)

    return {
        "query": entry.query,
        "expected_ids": entry.expected_ids,
        "type": entry.query_type,
        "source_book": entry.source_book,
        "semantic_rank": semantic_rank,
        "reranked_rank": reranked_rank,
        "semantic_top3": semantic_ids[:3],
        "reranked_top3": reranked_ids[:3],
    }


def _reciprocal_rank_fusion(
    semantic_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """Merge two ranked lists using Reciprocal Rank Fusion (RRF)."""
    scores: dict[str, float] = {}
    chunk_map: dict[str, dict] = {}

    for rank, chunk in enumerate(semantic_results, 1):
        cid = chunk.get("id", "")
        scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank)
        chunk_map[cid] = chunk

    for rank, chunk in enumerate(bm25_results, 1):
        cid = chunk.get("id", "")
        scores[cid] = scores.get(cid, 0) + 1.0 / (k + rank)
        if cid not in chunk_map:
            chunk_map[cid] = chunk

    sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)
    merged: list[dict] = []
    for cid in sorted_ids:
        item = dict(chunk_map[cid])
        item["rrf_score"] = round(scores[cid], 6)
        merged.append(item)
    return merged


def evaluate_entry_hybrid(
    index: KardecIndex,
    bm25: BM25Index,
    query_vec: np.ndarray,
    entry: GoldEntry,
    *,
    broad_k: int,
    candidate_k: int,
    top_k: int,
) -> dict:
    expected = set(entry.expected_ids)

    semantic_results = index.search(query_vec, top_k=broad_k)
    bm25_results = bm25.search(entry.query, top_k=broad_k)

    # RRF merge
    fused = _reciprocal_rank_fusion(semantic_results, bm25_results)
    fused_ids = [c.get("id", "") for c in fused]
    hybrid_rank = _first_hit_rank(fused_ids, expected)

    # Hybrid + question rerank
    hybrid_reranked = rerank_question_matches(entry.query, fused[:candidate_k], top_k=top_k)
    hybrid_reranked_ids = [c.get("id", "") for c in hybrid_reranked]
    hybrid_reranked_rank = _first_hit_rank(hybrid_reranked_ids, expected)

    return {
        "query": entry.query,
        "expected_ids": entry.expected_ids,
        "type": entry.query_type,
        "source_book": entry.source_book,
        "hybrid_rank": hybrid_rank,
        "hybrid_reranked_rank": hybrid_reranked_rank,
        "hybrid_top3": fused_ids[:3],
        "hybrid_reranked_top3": hybrid_reranked_ids[:3],
    }


def _compute_metrics(rows: list[dict], strategy_key: str) -> dict:
    ranks = [r[strategy_key] for r in rows]
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
    parser = argparse.ArgumentParser(description="Evaluate retrieval against gold dataset.")
    parser.add_argument("--gold", default="evals/data/gold_retrieval_300.json")
    parser.add_argument("--index-dir", default="backend/data/kardec/index")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--candidate-k", type=int, default=50)
    parser.add_argument("--broad-k", type=int, default=120)
    parser.add_argument("--show-misses", type=int, default=10)
    parser.add_argument("--hybrid", action="store_true", help="Also run hybrid BM25+semantic")
    parser.add_argument("--chunks-dir", default="backend/data/kardec/chunks")
    parser.add_argument("--output", default="evals/results/retrieval_eval_latest.json")
    args = parser.parse_args()

    entries = load_gold(Path(args.gold))
    print(f"Loaded {len(entries)} gold entries")

    index = KardecIndex.load(Path(args.index_dir), name="kardec")
    embedder = Embedder(model_name=settings.EMBEDDING_MODEL)

    # Batch encode
    t0 = time.perf_counter()
    vectors = embedder.encode([e.query for e in entries])
    t_embed = time.perf_counter()
    print(f"Encoded {len(entries)} queries in {t_embed - t0:.1f}s")

    # Evaluate each entry
    rows: list[dict] = []
    for i, entry in enumerate(entries):
        result = evaluate_entry(
            index,
            np.atleast_2d(vectors[i]),
            entry,
            broad_k=args.broad_k,
            candidate_k=args.candidate_k,
            top_k=args.top_k,
        )
        rows.append(result)

    t_eval = time.perf_counter()
    print(f"Evaluated {len(rows)} queries in {t_eval - t_embed:.1f}s")

    # --- Hybrid BM25+semantic ---
    hybrid_rows: list[dict] = []
    if args.hybrid:
        bm25 = BM25Index.from_chunks_dir(Path(args.chunks_dir))
        t_bm25 = time.perf_counter()
        print(f"BM25 index built in {t_bm25 - t_eval:.1f}s")
        for i, entry in enumerate(entries):
            result = evaluate_entry_hybrid(
                index,
                bm25,
                np.atleast_2d(vectors[i]),
                entry,
                broad_k=args.broad_k,
                candidate_k=args.candidate_k,
                top_k=args.top_k,
            )
            hybrid_rows.append(result)
        t_hybrid = time.perf_counter()
        print(f"Hybrid eval: {len(hybrid_rows)} queries in {t_hybrid - t_bm25:.1f}s")

    # --- Aggregate metrics ---
    summary: dict = {
        "total_entries": len(rows),
        "config": {
            "top_k": args.top_k,
            "candidate_k": args.candidate_k,
            "broad_k": args.broad_k,
            "hybrid": args.hybrid,
        },
    }

    # Overall
    summary["overall_semantic"] = _compute_metrics(rows, "semantic_rank")
    summary["overall_reranked"] = _compute_metrics(rows, "reranked_rank")

    # By type
    summary["by_type"] = {}
    for qtype in ("exact_question", "near_paraphrase", "conceptual_query"):
        subset = [r for r in rows if r["type"] == qtype]
        if subset:
            summary["by_type"][qtype] = {
                "semantic": _compute_metrics(subset, "semantic_rank"),
                "reranked": _compute_metrics(subset, "reranked_rank"),
            }

    # By book
    summary["by_book"] = {}
    for book in ("lde", "ese", "cei", "gen", "ldm"):
        subset = [r for r in rows if r["source_book"] == book]
        if subset:
            summary["by_book"][book] = {
                "semantic": _compute_metrics(subset, "semantic_rank"),
                "reranked": _compute_metrics(subset, "reranked_rank"),
            }

    # Hybrid metrics
    if hybrid_rows:
        summary["overall_hybrid"] = _compute_metrics(hybrid_rows, "hybrid_rank")
        summary["overall_hybrid_reranked"] = _compute_metrics(hybrid_rows, "hybrid_reranked_rank")
        summary["by_type_hybrid"] = {}
        for qtype in ("exact_question", "near_paraphrase", "conceptual_query"):
            subset = [r for r in hybrid_rows if r["type"] == qtype]
            if subset:
                summary["by_type_hybrid"][qtype] = {
                    "hybrid": _compute_metrics(subset, "hybrid_rank"),
                    "hybrid_reranked": _compute_metrics(subset, "hybrid_reranked_rank"),
                }

    # Misses (use best strategy available)
    best_key = "hybrid_reranked_rank" if hybrid_rows else "reranked_rank"
    best_rows = hybrid_rows if hybrid_rows else rows
    misses = [r for r in best_rows if r[best_key] is None]
    summary["miss_count"] = len(misses)
    summary["misses"] = misses[: args.show_misses]

    # Print table
    print("\n" + "=" * 80)
    print(
        f"{'Strategy':<25} {'R@1':>6} {'R@3':>6} {'R@5':>6} {'R@10':>6} {'MRR':>6} {'NDCG@10':>8}"
    )
    print("-" * 80)
    strategy_rows = [
        ("Semantic baseline", "overall_semantic"),
        ("Question rerank", "overall_reranked"),
    ]
    if hybrid_rows:
        strategy_rows.extend(
            [
                ("Hybrid RRF", "overall_hybrid"),
                ("Hybrid + Q-rerank", "overall_hybrid_reranked"),
            ]
        )
    for label, key in strategy_rows:
        m = summary[key]
        print(
            f"{label:<25} {m['recall@1']:>6.2f} {m['recall@3']:>6.2f} {m['recall@5']:>6.2f} {m['recall@10']:>6.2f} {m['mrr']:>6.2f} {m['ndcg@10']:>8.2f}"
        )

    print("\n--- By query type (best strategy) ---")
    type_data = summary.get("by_type_hybrid", summary["by_type"])
    type_key = "hybrid_reranked" if hybrid_rows else "reranked"
    for qtype, data in type_data.items():
        m = data[type_key]
        print(f"  {qtype:<22} R@10={m['recall@10']:.2f}  MRR={m['mrr']:.2f}  n={m['count']}")

    print(f"\nTotal misses: {summary['miss_count']}")
    if misses:
        print("\nSample misses:")
        top3_key = "hybrid_reranked_top3" if hybrid_rows else "reranked_top3"
        for miss in misses[: args.show_misses]:
            print(f"  query: {miss['query'][:80]}")
            print(f"    expected: {miss['expected_ids']}")
            print(f"    got top3: {miss.get(top3_key, [])}")
            print()

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Results saved to {output_path}")

    # Pass if reranked recall@10 >= 0.7
    passed = summary["overall_reranked"]["recall@10"] >= 0.7
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
