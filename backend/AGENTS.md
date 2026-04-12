# AGENTS.md — Backend

> Scope: everything under `backend/`.
> Also read the root [`../AGENTS.md`](../AGENTS.md) for project-wide rules.

---

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| API framework | FastAPI + Uvicorn |
| LLM (Apple Silicon) | mlx-lm (`mlx-community/gemma-4-E4B-it-4bit`) |
| LLM (CUDA) | HuggingFace Transformers + BitsAndBytes 4-bit |
| LLM (CPU fallback) | HuggingFace Transformers fp32 |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` |
| Vector search | FAISS `IndexFlatIP` |
| Config | pydantic-settings (reads `backend/.env`) |
| Linting / formatting | ruff (config in root `pyproject.toml`) |

---

## Running the backend

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Health check: `GET http://localhost:8000/api/health`

---

## Module map

```
app/
├── main.py          ← FastAPI lifespan: loads index then model
├── config.py        ← Settings (MODEL_ID, HF_TOKEN, etc.)
├── state.py         ← Module-level singletons (rag, index)
│
├── api/
│   ├── models.py    ← Pydantic request/response schemas
│   └── routes/
│       ├── chat.py  ← POST /api/chat (SSE streaming)
│       ├── search.py← POST /api/search
│       └── health.py← GET /api/health
│
├── corpus/
│   ├── parser.py    ← PDF → raw text (pdfminer)
│   ├── chunker.py   ← Raw text → JSONL chunks with metadata
│   ├── embedder.py  ← Chunks → L2-normalised float32 vectors
│   └── indexer.py   ← Vectors → FAISS IndexFlatIP + metadata store
│
├── llm/
│   └── engine.py    ← load() / stream_tokens() / astream_tokens()
│                       Auto-detects: MPS→MLX, CUDA→HF, else CPU
│
├── persona/
│   ├── prompts.py   ← System prompt builder per persona
│   └── rag.py       ← RAGOrchestrator: retrieve → prompt → stream
│
└── cache/           ← TurboQuantCache (Phase 2, not yet implemented)
```

---

## API contract

### `POST /api/chat`

Request body (`ChatRequest`):
```json
{
  "message": "string (1–4096 chars)",
  "persona_id": "kardec",
  "session_id": "uuid-string | null",
  "history": [{"role": "user|assistant", "content": "string"}],
  "options": {
    "max_new_tokens": 1024,
    "top_k_chunks": 5,
    "temperature": 0.7
  }
}
```

SSE event stream response:
```
event: token
data: {"token": "..."}

event: citations
data: {"citations": [{...}]}

event: stats
data: {"stats": {"session_id": "...", "tokens_generated": N, ...}}

event: done
data: [DONE]
```

### `GET /api/health`

```json
{
  "status": "ok | degraded | error",
  "model_loaded": true,
  "index_loaded": true,
  "persona_available": ["kardec"],
  "vram_used_mb": null,
  "vram_total_mb": null,
  "version": "0.1.0"
}
```

---

## LLM engine rules

- **Apple Silicon (MPS detected):** use `mlx_lm.load()` + `mlx_lm.stream_generate()`.
  Temperature is passed via `make_sampler(temperature)` from `mlx_lm.sample_utils` —
  **not** as a direct kwarg (the `temp=` and `temperature=` kwargs were removed in mlx-lm ≥ 0.22).
- **CUDA:** HuggingFace Transformers + BitsAndBytes 4-bit. Use `dtype=` not `torch_dtype=`.
- **CPU:** HuggingFace Transformers fp32. Warn user it is slow.
- Never import BitsAndBytes on MPS — it is CUDA-only and will crash.
- `_model` and `_tokenizer` are module-level singletons. Rebind to local variables
  after `assert _model is not None` to satisfy Pyright type narrowing.

---

## Corpus pipeline

Ingestion via `ingest.sh` at the repo root:
```bash
./ingest.sh          # default: lde only
./ingest.sh lde ldm  # multiple books
```

Manual steps if needed:
```bash
PYTHONPATH=backend python -m app.corpus.parser \
  --source books/ --output backend/data/kardec/chunks/ --book lde --validate

PYTHONPATH=backend python -m app.corpus.indexer \
  --chunks backend/data/kardec/chunks/ --output backend/data/kardec/index/
```

### Chunk metadata schema
```json
{
  "id": "lde-q223",
  "obra": "O Livro dos Espíritos",
  "parte": "Parte Segunda — Do Mundo Espírita",
  "capitulo": "Capítulo I — Os Espíritos",
  "questao": 223,
  "texto": "..."
}
```

### Chunking targets

| Book | Unit | Expected count |
|---|---|---|
| LdE | One chunk per numbered question | 1,019 |
| LdM | One chunk per numbered article | 334 |
| ESE | Paragraph + 2-paragraph overlap, per chapter | — |
| CeI | Paragraph + 2-paragraph overlap, per part | — |
| Gen | Paragraph + 2-paragraph overlap, per chapter | — |

---

## Code conventions

- **Line length:** 100 (ruff enforces this).
- **Quotes:** double (ruff-format enforces this).
- **Type hints:** required on all public functions. Use `from __future__ import annotations`.
- **Frozen dataclasses** for quantized representations (`QuantizedMSE`, `QuantizedProd`).
- **No bare `except:`** — always catch a specific exception or `Exception` at minimum.
- **Logging:** `logger = logging.getLogger("module.name")` — never `print()`.
- **No commented-out code** — delete it. Git history preserves it if needed.

---

## Testing

```bash
cd backend && source venv/bin/activate
pytest tests/ -v
```

Tests mirror `app/` structure: `tests/corpus/`, `tests/api/`, `tests/llm/`, etc.

---

## Hygiene checklist (before every commit)

- [ ] `pre-commit run --all-files` — all hooks green
- [ ] No unused imports (ruff F401)
- [ ] No unused variables or dead functions
- [ ] No module files that nothing imports anymore
- [ ] Server starts cleanly: `uvicorn app.main:app`

---

> Also read: [`../AGENTS.md`](../AGENTS.md) · [`../evals/AGENTS.md`](../evals/AGENTS.md)
