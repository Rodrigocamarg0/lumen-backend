# CLAUDE.md — Claude Code Instructions

Loaded automatically at session start. Follow without exception.

---

## Read the right AGENTS.md first

| Working in… | Read this |
|---|---|
| Anything | [`AGENTS.md`](./AGENTS.md) |
| `backend/` | [`backend/AGENTS.md`](./backend/AGENTS.md) |
| `frontend/` | [`frontend/AGENTS.md`](./frontend/AGENTS.md) |
| `evals/` | [`evals/AGENTS.md`](./evals/AGENTS.md) |

---

## Pre-commit — mandatory before every commit

```bash
pre-commit run --all-files
```

First time in a new clone:
```bash
pip install pre-commit && pre-commit install
```

Never use `--no-verify`.

---

## Repository hygiene — apply after every change

- **Delete dead code** — unused functions, imports, variables. No comment-outs.
- **Fix deprecated usages** — update to current APIs now, no shims.
- **Delete orphan files** — if nothing imports it, delete it.
- **No stale TODO/FIXME** — fix it or delete it.
- After a refactor, search for references to removed symbols:
  ```bash
  grep -r "RemovedSymbol" backend/ frontend/
  ```

---

## Quick-start

```bash
# Backend
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev       # :3000, proxies /api → :8000
cd frontend && npm run build     # production build

# Corpus ingestion
./ingest.sh                      # lde only (default)
./ingest.sh lde ldm ese
```

---

## Commit format

```
[Phase N] <verb> <what>

[Phase 1] Fix MLX sampler parameter in engine.py
[Phase 1] Remove dead StaticFiles import
[Phase 2] Add TurboQuantMSE cache wrapper
```
