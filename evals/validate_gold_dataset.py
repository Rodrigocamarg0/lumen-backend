"""
Validate the gold retrieval dataset structure and references.

Checks:
  - JSON schema (required fields, types)
  - expected_ids reference real chunk IDs
  - No duplicate queries
  - Distribution report

Run from repo root:
    python evals/validate_gold_dataset.py
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

GOLD_PATH = Path("evals/data/gold_retrieval_300.json")
CHUNKS_DIR = Path("backend/data/kardec/chunks")


def load_all_chunk_ids() -> set[str]:
    ids: set[str] = set()
    for jsonl in CHUNKS_DIR.glob("*.jsonl"):
        with jsonl.open(encoding="utf-8") as fh:
            for line in fh:
                chunk = json.loads(line)
                ids.add(chunk["id"])
    return ids


def main() -> int:
    data = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    chunk_ids = load_all_chunk_ids()
    print(f"Corpus has {len(chunk_ids)} chunk IDs")

    errors: list[str] = []
    seen_queries: set[str] = set()
    type_counts: Counter[str] = Counter()
    book_counts: Counter[str] = Counter()

    for i, entry in enumerate(data):
        # Schema check
        for field in ("query", "expected_ids", "type"):
            if field not in entry:
                errors.append(f"Entry {i}: missing field '{field}'")

        if not isinstance(entry.get("expected_ids"), list):
            errors.append(f"Entry {i}: expected_ids must be a list")
            continue

        # Check IDs exist
        for eid in entry["expected_ids"]:
            if eid not in chunk_ids:
                errors.append(f"Entry {i}: unknown chunk ID '{eid}' (query: {entry['query'][:50]})")

        # Duplicate check
        key = entry["query"].strip().lower()
        if key in seen_queries:
            errors.append(f"Entry {i}: duplicate query '{entry['query'][:50]}'")
        seen_queries.add(key)

        type_counts[entry.get("type", "unknown")] += 1
        book_counts[entry.get("source_book", "unknown")] += 1

    # Report
    print(f"\nTotal entries: {len(data)}")
    print("\nBy type:")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")
    print("\nBy book:")
    for b, c in sorted(book_counts.items()):
        print(f"  {b}: {c}")

    if errors:
        print(f"\n❌ {len(errors)} errors found:")
        for err in errors[:20]:
            print(f"  - {err}")
        return 1

    print("\n✅ All checks passed!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
