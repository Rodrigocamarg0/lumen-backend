#!/usr/bin/env bash
# ingest.sh — corpus ingestion pipeline for Lumen
#
# Usage:
#   ./ingest.sh              # process all configured books
#   ./ingest.sh lde          # process one book (lde | ldm | ese | cei | gen)
#   ./ingest.sh lde ldm      # process multiple books
#
# What it does:
#   1. Parses each PDF into JSONL chunks  (backend/data/kardec/chunks/)
#   2. Builds / updates the FAISS index   (backend/data/kardec/index/)
#
# After a successful run, restart the backend — it will load the new index on startup.

set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
BOOKS_DIR="$SCRIPT_DIR/books"
CHUNKS_DIR="$BACKEND_DIR/data/kardec/chunks"
INDEX_DIR="$BACKEND_DIR/data/kardec/index"
VENV="$BACKEND_DIR/venv"

# ── Books available ───────────────────────────────────────────────────────────
#   lde  O Livro dos Espíritos
#   ldm  O Livro dos Médiuns
#   ese  O Evangelho Segundo o Espiritismo
#   cei  O Céu e o Inferno
#   gen  A Gênese

DEFAULT_BOOKS=(lde)

# ── Colours ──────────────────────────────────────────────────────────────────

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

step()  { echo -e "\n${BOLD}▸ $*${RESET}"; }
ok()    { echo -e "${GREEN}✓ $*${RESET}"; }
warn()  { echo -e "${YELLOW}⚠ $*${RESET}"; }
fail()  { echo -e "${RED}✗ $*${RESET}"; exit 1; }

# ── Pre-flight checks ─────────────────────────────────────────────────────────

step "Pre-flight checks"

# Source .env so HF_TOKEN (and any other vars) are available to subprocesses
ENV_FILE="$BACKEND_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
    ok ".env loaded from $ENV_FILE"
else
    warn ".env not found at $ENV_FILE — HuggingFace token may be missing"
fi

[[ -d "$VENV" ]] || fail "venv not found at $VENV — run: cd backend && python -m venv venv && pip install -r requirements.txt"

PYTHON="$VENV/bin/python"
[[ -x "$PYTHON" ]] || fail "Python not found in venv"

[[ -d "$BOOKS_DIR" ]] || fail "Books directory not found: $BOOKS_DIR"

ok "venv: $PYTHON"
ok "books: $BOOKS_DIR"

mkdir -p "$CHUNKS_DIR" "$INDEX_DIR"

# ── Resolve which books to process ───────────────────────────────────────────

if [[ $# -gt 0 ]]; then
    BOOKS=("$@")
else
    BOOKS=("${DEFAULT_BOOKS[@]}")
fi

echo "Books to process: ${BOOKS[*]}"

# ── Step 1: Parse PDFs → JSONL chunks ────────────────────────────────────────

step "Step 1/2 — Parsing PDFs into chunks"

PARSE_OK=true
for BOOK in "${BOOKS[@]}"; do
    echo ""
    echo "  Parsing: $BOOK"
    if PYTHONPATH="$BACKEND_DIR" "$PYTHON" -m app.corpus.parser \
        --source "$BOOKS_DIR" \
        --output "$CHUNKS_DIR" \
        --book "$BOOK" \
        --validate 2>&1 | sed 's/^/    /'; then
        ok "  $BOOK — chunks written to $CHUNKS_DIR"
    else
        warn "  $BOOK — parser returned non-zero exit"
        PARSE_OK=false
    fi
done

$PARSE_OK || fail "One or more books failed to parse. Fix the errors above before indexing."

# ── Step 2: Build FAISS index ─────────────────────────────────────────────────

step "Step 2/2 — Building FAISS index"
echo "  Input:  $CHUNKS_DIR"
echo "  Output: $INDEX_DIR"
echo ""

if PYTHONPATH="$BACKEND_DIR" "$PYTHON" -m app.corpus.indexer \
    --chunks "$CHUNKS_DIR" \
    --output "$INDEX_DIR" \
    2>&1 | sed 's/^/    /'; then
    ok "Index built → $INDEX_DIR"
else
    fail "Indexer failed. Check the output above."
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}────────────────────────────────────────${RESET}"
echo -e "${GREEN}${BOLD} Ingestion complete${RESET}"
echo -e "${BOLD}────────────────────────────────────────${RESET}"
echo ""

CHUNK_COUNT=0
for BOOK in "${BOOKS[@]}"; do
    JSONL="$CHUNKS_DIR/${BOOK}_chunks.jsonl"
    if [[ -f "$JSONL" ]]; then
        N=$(wc -l < "$JSONL" | tr -d ' ')
        echo "  $BOOK  →  $N chunks"
        CHUNK_COUNT=$((CHUNK_COUNT + N))
    fi
done

INFO_FILE="$INDEX_DIR/kardec_info.json"
if [[ -f "$INFO_FILE" ]]; then
    TOTAL_VECTORS=$(python3 -c "import json; d=json.load(open('$INFO_FILE')); print(d.get('total_vectors','?'))" 2>/dev/null || echo "?")
    echo ""
    echo "  FAISS index: $TOTAL_VECTORS vectors"
fi

echo ""
echo "  Restart the backend to load the new index:"
echo "    cd backend && source venv/bin/activate"
echo "    uvicorn app.main:app --reload --port 8000"
echo ""
