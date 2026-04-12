# AGENTS.md — Lumen (Root)

> Central guide for every AI agent working on this repository.
> Read this file first, then follow the pointer to the sub-agent file
> that matches the directory you are working in.

---

## Sub-agent files — read the closest one to your task

| Directory | File | When to read it |
|---|---|---|
| `backend/` | [`backend/AGENTS.md`](./backend/AGENTS.md) | Any Python / FastAPI / MLX / corpus work |
| `frontend/` | [`frontend/AGENTS.md`](./frontend/AGENTS.md) | Any React / Vite / Tailwind work |
| `evals/` | [`evals/AGENTS.md`](./evals/AGENTS.md) | Any benchmark / evaluation script work |

The root `AGENTS.md` (this file) defines **project-wide** rules that every agent must follow
regardless of which sub-directory they are working in.

---

## Project overview

**Lumen** enables users to converse with simulated personas of Spiritist authors using:

- **Gemma 4 E4B** (4B dense model, head_dim=256, 128K context) as the base LLM
- **RAG** over each author's complete corpus via FAISS inner-product search
- **TurboQuant KV cache compression** (Phase 2) for memory-efficient long sessions
- **FastAPI + SSE** backend, **React 18 + Vite** frontend — fully local, no cloud

Current phase: **Phase 1 — MVP** (Kardec 5 books, Kardec persona only).

---

## Repository layout

```
lumen/
├── AGENTS.md               ← You are here (root orchestrator)
├── CLAUDE.md               ← Claude Code-specific instructions
├── pyproject.toml          ← Ruff + Pyright config (Python tooling)
├── .pre-commit-config.yaml ← Pre-commit hooks (ruff, prettier, hygiene)
├── .gitignore
├── ingest.sh               ← Corpus ingestion script
│
├── backend/                ← FastAPI app (Python 3.11+)
│   ├── AGENTS.md           ← Backend agent guide ← READ THIS for backend work
│   ├── app/
│   │   ├── api/            ← Routes + Pydantic models
│   │   ├── corpus/         ← Parser, chunker, embedder, indexer
│   │   ├── llm/            ← MLX / CUDA / CPU engine
│   │   ├── persona/        ← Prompts + RAG orchestrator
│   │   └── cache/          ← TurboQuantCache (Phase 2)
│   ├── tests/
│   └── requirements.txt
│
├── frontend/               ← React 18 + Vite + Tailwind CSS
│   ├── AGENTS.md           ← Frontend agent guide ← READ THIS for frontend work
│   └── src/
│
├── evals/                  ← Benchmark + evaluation scripts
│   ├── AGENTS.md           ← Evals agent guide ← READ THIS for eval work
│   ├── turboquant_eval.py  ← 30 algorithm checks (Phase 2)
│   ├── kv_cache_eval.py    ← Memory / PPL / needle (Phase 2)
│   └── persona_eval.py     ← Style fidelity / RAG recall
│
├── specs/                  ← Architecture decisions, requirements, tasks
├── docker/                 ← Docker Compose + Dockerfiles
└── external/               ← Cloned reference implementations (Phase 2)
```

---

## Critical algorithmic rules (non-negotiable)

These apply to every agent. Violating them corrupts results silently.

| Rule | Detail |
|---|---|
| **TurboQuantMSE for K and V** | Never use TurboQuantProd for keys — QJL residual variance is amplified by softmax |
| **Codebooks must match head_dim=256** | Do not reuse d=128 codebooks from Llama/Mistral |
| **Default bit budget: 3.5-bit** | Mixed precision: top 5–20% K channels by RMS → 8-bit, rest → 3-bit |
| **FAISS uses inner product** | Always `IndexFlatIP` — TurboQuant is designed for IP, not cosine |
| **Real speedup is ~1.85×** | Never claim or assume the paper's 8× figure |
| **No dequantization mid-computation** | Operate on compressed indices; dequantize only for final output |

---

## Repository hygiene (mandatory after every change)

Every agent must leave the codebase **cleaner** than they found it.

### After any edit or refactor

1. **Remove dead code** — delete unused functions, classes, imports, and variables.
   Comment-outs are not acceptable; delete entirely.
2. **Remove deprecated usages** — if a library API changed, update the call site immediately.
   No compatibility shims unless load-bearing.
3. **No orphan files** — if a module is no longer imported anywhere, delete it.
4. **No TODO/FIXME without an issue** — either fix it now or delete the comment.
5. **Run pre-commit before committing** — all hooks must pass:
   ```bash
   pre-commit run --all-files
   ```
   Never commit with `--no-verify`.

### Import discipline

- **Python:** standard library → third-party → `app.*` (enforced by ruff/isort)
- **JavaScript:** React → third-party → local components → `lib/`

### Commit format

```
[Phase N] <verb> <what>

Examples:
  [Phase 1] Fix MLX stream_generate sampler parameter
  [Phase 1] Remove dead StaticFiles import from main.py
  [Phase 2] Implement TurboQuantMSE cache wrapper
```

---

## Development phases

| Phase | Status | Gate criteria |
|---|---|---|
| **1 — MVP** | ← current | Kardec persona end-to-end, 5 books indexed, SSE streaming works |
| **2 — TurboQuant** | blocked on Phase 1 | 30/30 algorithm checks, ≥5× KV compression, <1% PPL degradation |
| **3 — Multi-persona** | blocked on Phase 2 | Emmanuel, André Luiz, Joanna; NIHS >95% at all context lengths |
| **4 — TTS & Polish** | blocked on Phase 3 | Optional; audio synthesis |

Do not start a phase until its predecessor's gate is met.

---

## Key numbers

| Metric | Target | Source |
|---|---|---|
| MSE at 3-bit, d=256 | ≤ 0.035 | TurboQuant paper Table 1 (1.2× tolerance) |
| MSE at 4-bit, d=256 | ≤ 0.011 | TurboQuant paper Table 1 (1.2× tolerance) |
| KV compression ratio | ≥ 5× | Requirements spec |
| Real attention speedup | ~1.85× (not 8×) | OmarHory benchmarks |
| RAG Recall@10 | > 0.90 | Requirements spec |
| Citation precision | > 90% | Requirements spec |
| NIHS recall | > 95% at 4K/16K/64K/128K | Requirements spec |
| LdE questions | 1,019 | Corpus analysis |

---

> **Last updated:** 2026-04-12
> Update this file when the architecture changes or a phase gate is passed.
