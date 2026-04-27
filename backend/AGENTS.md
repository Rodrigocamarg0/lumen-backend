# AGENTS.md — Backend

> Scope: `backend/`.
> Also read: [`../AGENTS.md`](../AGENTS.md)

---

## Stack

Python 3.11+ · FastAPI · Uvicorn · FAISS · OpenAI API · Supabase Auth · SQLAlchemy/Postgres · pydantic-settings

---

## Run

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
# health check: GET http://localhost:8000/api/health
```

---

## Module map

```
app/
├── main.py        ← FastAPI entry point, lifespan (loads index then model)
├── config.py      ← Settings from .env (MODEL_ID, HF_TOKEN, etc.)
├── state.py       ← Module-level singletons (rag, index)
├── api/
│   ├── models.py  ← Pydantic request/response schemas
│   └── routes/    ← chat.py · search.py · health.py
├── corpus/        ← parser · chunker · embedder · indexer
├── llm/           ← engine.py (external OpenAI provider)
├── persona/       ← prompts.py · rag.py (RAGOrchestrator)
└── cache/         ← TurboQuantCache (Phase 2, not yet implemented)
```

**Reference docs:**
- API contract (endpoints, request/response schemas, SSE events): `specs/architecture/api_contract.md`
- LLM engine rules (external OpenAI provider): `../docs/llm-engine.md`
- Corpus parsing and chunk metadata: `specs/architecture/parsing_strategy.md`

---

## Corpus ingestion

```bash
./ingest.sh              # default: lde only (run from repo root)
./ingest.sh lde ldm ese  # multiple books
```

---

## Tests

```bash
cd backend
uv run pytest tests/ -v
```

Mirror `app/` structure in `tests/`: `tests/corpus/`, `tests/api/`, `tests/llm/`, etc.

---

## Code conventions

- Line length: **100** (ruff enforces)
- Quotes: **double** (ruff-format enforces)
- Type hints on all public functions; use `from __future__ import annotations`
- Logging: `logger = logging.getLogger("module.name")` — never `print()`
- No bare `except:` — catch `Exception` or a specific type
- No commented-out code — delete it

---

## Hygiene checklist (before every commit)

- [ ] `pre-commit run --all-files` — all hooks green
- [ ] No unused imports (ruff F401), no dead functions
- [ ] No module files that nothing imports
- [ ] Server starts: `uv run uvicorn app.main:app`

---

> See also: [`../AGENTS.md`](../AGENTS.md) · [`../docs/llm-engine.md`](../docs/llm-engine.md) · [`../specs/architecture/api_contract.md`](../specs/architecture/api_contract.md)
