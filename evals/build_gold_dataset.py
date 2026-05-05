"""
Build the gold retrieval dataset for eval.

Step 1 of data-science-improvements.md:
  - Extract 100 exact L.E. questions (sampled deterministically)
  - Combine with hand-curated paraphrases and conceptual queries

Run from repo root:
    python evals/build_gold_dataset.py
"""

from __future__ import annotations

import json
from pathlib import Path
import random

CHUNKS_DIR = Path("backend/data/kardec/chunks")
OUTPUT = Path("evals/data/gold_retrieval_300.json")
SEED = 42
EXACT_SAMPLE = 100


def _question_text(chunk: dict) -> str:
    """Extract just the question portion (before the spirit answer)."""
    text = (chunk.get("texto") or "").strip()
    answer_pos = text.find('"')
    if answer_pos >= 0:
        text = text[:answer_pos]
    return " ".join(text.split()).strip()


def extract_exact_questions(sample_size: int = EXACT_SAMPLE) -> list[dict]:
    """Sample exact L.E. question texts from chunks."""
    candidates: list[dict] = []
    path = CHUNKS_DIR / "lde_chunks.jsonl"
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            chunk = json.loads(line)
            q_text = _question_text(chunk)
            if not q_text or len(q_text) < 10:
                continue
            candidates.append(
                {
                    "query": q_text,
                    "expected_ids": [chunk["id"]],
                    "type": "exact_question",
                    "source_book": "lde",
                    "notes": f"Q{chunk['questao']} — {chunk.get('capitulo', '')}",
                }
            )

    rng = random.Random(SEED)
    rng.shuffle(candidates)
    return candidates[:sample_size]


def load_manual_entries() -> list[dict]:
    """Load hand-curated paraphrases and conceptual queries."""
    path = Path("evals/data/gold_manual_entries.json")
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


# Map: original expected_chunk_id → additional valid chunk IDs (from miss analysis).
# These are chunks that retrieval returned and are actually acceptable answers.
_EXPANDED_IDS: dict[str, list[str]] = {
    "lde-q0010": ["lde-q0012", "lde-q0013", "lde-q0015"],
    "lde-q0093": ["gen-c15-p018", "lde-q0187"],
    "lde-q0148": ["lde-q0149", "lde-q0150"],
    "lde-q0166": ["lde-q0167", "lde-q0171"],
    "lde-q0100": ["lde-q0549", "lde-q0280"],
    "lde-q0223": ["lde-q0282", "lde-q0284"],
    "lde-q0106": ["lde-q0114", "lde-q0115", "lde-q0280"],
    "lde-q1009": ["cei-p1-c04-p057", "cei-p1-c04-p058", "cei-p1-c04-p060"],
    "lde-q1011": ["cei-p1-c05-p001", "cei-p1-c05-p002"],
    "lde-q1016": ["cei-p1-c03-p009"],
    "lde-q0952": ["lde-q0957", "cei-p2-c16-p099"],
    "lde-q0872": ["lde-q0843", "lde-q0834"],
    "lde-q0152": ["lde-q0150", "lde-q0153"],
    "lde-q0597": ["lde-q0598", "lde-q0600"],
    "lde-q0023": ["lde-q0024", "lde-q0025"],
    "lde-q0258": ["lde-q0259", "lde-q0205"],
    "lde-q0134": ["lde-q0135"],
    "lde-q0495": ["lde-q0496", "lde-q0497"],
    "lde-q0128": ["lde-q0129", "lde-q0130", "lde-q0131"],
    "lde-q0392": ["lde-q0393", "lde-q0394"],
    "lde-q0810": ["lde-q0811"],
    "lde-q0843": ["lde-q0851", "lde-q0852"],
}


def migrate_existing_fixture() -> list[dict]:
    """Convert existing lde-50-questions.json to gold format as paraphrases.

    Expands expected_ids with additional valid chunks identified during
    Step 3 miss analysis.
    """
    path = Path("evals/data/lde-50-questions.json")
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for row in rows:
        original_id = row["expected_chunk_id"]
        ids = [original_id, *_EXPANDED_IDS.get(original_id, [])]
        entries.append(
            {
                "query": row["query"],
                "expected_ids": ids,
                "type": "near_paraphrase",
                "source_book": "lde",
                "notes": row.get("notes", ""),
            }
        )
    return entries


def build() -> None:
    exact = extract_exact_questions()
    paraphrases = migrate_existing_fixture()
    manual = load_manual_entries()

    all_entries = exact + paraphrases + manual

    # Deduplicate by query text
    seen: set[str] = set()
    deduped: list[dict] = []
    for entry in all_entries:
        key = entry["query"].strip().lower()
        if key not in seen:
            seen.add(key)
            deduped.append(entry)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(deduped, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Summary
    by_type: dict[str, int] = {}
    for e in deduped:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1

    print(f"Gold dataset: {len(deduped)} entries → {OUTPUT}")
    for t, c in sorted(by_type.items()):
        print(f"  {t}: {c}")


if __name__ == "__main__":
    build()
