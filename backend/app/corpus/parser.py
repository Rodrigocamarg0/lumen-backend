"""
PDF → JSONL extraction pipeline for the 5 Kardec books.

CLI usage:
    python -m app.corpus.parser \\
        --source /path/to/books/ \\
        --output backend/data/kardec/chunks/ \\
        --book lde          # lde | ldm | ese | cei | gen | all
        --validate
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
from pathlib import Path
import sys

from pdfminer.high_level import extract_text
from pdfminer.layout import LAParams

from app.corpus.chunker import (
    extract_cei_chunks,
    extract_ese_chunks,
    extract_gen_chunks,
    extract_lde_chunks,
    extract_ldm_chunks,
    validate_chunks,
)

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger("parser")

# ---------------------------------------------------------------------------
# Book registry
# ---------------------------------------------------------------------------

BOOK_MAP: dict[str, dict] = {
    "lde": {
        "file": "WEB-Livro-dos-Espíritos-Guillon-1.pdf",
        "obra": "O Livro dos Espíritos",
        "extractor": extract_lde_chunks,
    },
    "ldm": {
        "file": "WEB-Livro-dos-Mediuns-Guillon-1.pdf",
        "obra": "O Livro dos Médiuns",
        "extractor": extract_ldm_chunks,
    },
    "ese": {
        "file": "WEB-O-Evangelho-segundo-o-Espiritismo-Guillon.pdf",
        "obra": "O Evangelho Segundo o Espiritismo",
        "extractor": extract_ese_chunks,
    },
    "cei": {
        "file": "WEB-O-Ceu-e-o-inferno-Guillon.pdf",
        "obra": "O Céu e o Inferno",
        "extractor": extract_cei_chunks,
    },
    "gen": {
        "file": "WEB-A-Genese-Guillon.pdf",
        "obra": "A Gênese",
        "extractor": extract_gen_chunks,
    },
}

# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------


def pdf_to_text(pdf_path: Path) -> str:
    """
    Extract raw text from a PDF using pdfminer with layout analysis tuned
    for single-column Portuguese books.
    """
    laparams = LAParams(
        line_margin=0.3,
        word_margin=0.1,
        char_margin=1.5,
        boxes_flow=0.5,
        detect_vertical=False,
    )
    logger.info(f"Reading {pdf_path.name} …")
    return extract_text(str(pdf_path), laparams=laparams)


# ---------------------------------------------------------------------------
# Per-book processing
# ---------------------------------------------------------------------------


def process_book(
    pdf_path: Path,
    book_id: str,
    output_dir: Path,
    do_validate: bool = True,
) -> list[dict]:
    """
    Extract, optionally validate, and write chunks for one book.
    Returns the list of chunks.
    """
    meta = BOOK_MAP[book_id]
    logger.info(f"Extracting «{meta['obra']}» …")

    raw_text = pdf_to_text(pdf_path)
    extractor = meta["extractor"]
    chunks = extractor(raw_text)

    logger.info(f"Extraction complete: {len(chunks)} chunks")

    if do_validate:
        errors = validate_chunks(chunks, book_id)
        if errors:
            for e in errors:
                logger.warning(f"Validation: {e}")
        else:
            logger.info("Validation OK")

    output_dir.mkdir(parents=True, exist_ok=True)
    out_jsonl = output_dir / f"{book_id}_chunks.jsonl"

    with open(out_jsonl, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    logger.info(f"Written → {out_jsonl}")
    _write_stats(chunks, book_id, meta["obra"], output_dir)

    return chunks


def _write_stats(
    chunks: list[dict],
    book_id: str,
    obra: str,
    output_dir: Path,
) -> None:
    if not chunks:
        return
    lengths = [len(c["texto"]) for c in chunks]
    partes = sorted({c.get("parte") for c in chunks if c.get("parte")})
    stats = {
        "book": obra,
        "book_id": book_id,
        "total_chunks": len(chunks),
        "total_chars": sum(lengths),
        "avg_chars_per_chunk": round(sum(lengths) / len(lengths)),
        "min_chars": min(lengths),
        "max_chars": max(lengths),
        "partes": list(partes),
        "extraction_date": datetime.datetime.utcnow().isoformat() + "Z",
    }
    out = output_dir / f"{book_id}_stats.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    logger.info(f"Stats → {out}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Lumen Corpus Parser")
    ap.add_argument("--source", required=True, help="Directory containing PDF books")
    ap.add_argument("--output", required=True, help="Directory for JSONL output")
    ap.add_argument(
        "--book",
        required=True,
        choices=[*BOOK_MAP.keys(), "all"],
        help="Book ID to parse, or 'all'",
    )
    ap.add_argument("--validate", action="store_true", help="Run post-extraction validation")
    args = ap.parse_args(argv)

    source_dir = Path(args.source)
    output_dir = Path(args.output)
    targets = list(BOOK_MAP.keys()) if args.book == "all" else [args.book]

    ok = True
    for book_id in targets:
        pdf_path = source_dir / BOOK_MAP[book_id]["file"]
        if not pdf_path.exists():
            logger.error(f"File not found: {pdf_path}")
            ok = False
            continue
        try:
            process_book(pdf_path, book_id, output_dir, do_validate=args.validate)
        except Exception as exc:
            logger.exception(f"Failed to process {book_id}: {exc}")
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
