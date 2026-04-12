# CLAUDE.md — Claude Code Instructions

This file is loaded automatically by Claude Code at session start.
These rules are non-negotiable and apply to every task.

---

## Agent hierarchy — always read the right AGENTS.md first

This project uses a layered agent system. Before touching any code, read:

| You are working on… | Read this file |
|---|---|
| Anything project-wide | [`AGENTS.md`](./AGENTS.md) |
| Python / FastAPI / MLX / corpus | [`backend/AGENTS.md`](./backend/AGENTS.md) |
| React / Vite / Tailwind | [`frontend/AGENTS.md`](./frontend/AGENTS.md) |
| Benchmarks / evals | [`evals/AGENTS.md`](./evals/AGENTS.md) |

The AGENTS.md files are the authoritative source of truth.
Do not duplicate their content here — refer to them.

---

## Pre-commit is mandatory

Run this before **every** commit, no exceptions:

```bash
pre-commit run --all-files
```

First time in a new clone:
```bash
pip install pre-commit && pre-commit install
```

Fix every failure before committing. Never use `--no-verify`.

---

## Repository hygiene (apply after every change)

This is the most important rule for keeping the project healthy:

1. **Delete dead code** — unused functions, classes, imports, variables. No comment-outs.
2. **Remove deprecated usages** — update to current APIs immediately, no shims.
3. **Delete orphan files** — if nothing imports a module, delete it.
4. **No stale TODO/FIXME** — fix it now or delete it.
5. After a refactor, grep for references to removed symbols and clean them up:
   ```bash
   grep -r "OldFunctionName" backend/ frontend/
   ```

---

## Quick-start commands

```bash
# Backend
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Frontend (dev)
cd frontend && npm run dev       # :3000, proxies /api → :8000
cd frontend && npm run build     # production build → dist/

# Corpus ingestion
./ingest.sh                      # lde only (default)
./ingest.sh lde ldm ese          # multiple books

# Pre-commit
pre-commit run --all-files
```

---

## Commit format

```
[Phase N] <verb> <what>

[Phase 1] Fix MLX sampler parameter in engine.py
[Phase 1] Remove dead StaticFiles import
[Phase 2] Add TurboQuantMSE cache wrapper
```

---

## Hard constraints

- **Never** use BitsAndBytes on Apple Silicon — it is CUDA-only.
- **Always** use `IndexFlatIP` for FAISS — not cosine, not L2.
- **Phase 1 only** until all Phase 1 gates are met (see `AGENTS.md`).
- **Never** commit `--no-verify`.
- **Never** add speculative code for future phases — implement when the phase starts.
