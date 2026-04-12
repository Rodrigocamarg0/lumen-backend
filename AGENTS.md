# AGENTS.md — Lumen (Root)

> Read this first. Then read the AGENTS.md closest to the directory you are working in.

---

## Sub-agent guides

| Working in… | Read this |
|---|---|
| `backend/` | [`backend/AGENTS.md`](./backend/AGENTS.md) |
| `frontend/` | [`frontend/AGENTS.md`](./frontend/AGENTS.md) |
| `evals/` | [`evals/AGENTS.md`](./evals/AGENTS.md) |

The sub-agent file takes precedence over this one for anything directory-specific.

---

## Where things live

```
lumen/
├── AGENTS.md               ← start here
├── CLAUDE.md               ← Claude Code session rules
├── pyproject.toml          ← ruff + pyright config
├── .pre-commit-config.yaml ← pre-commit hooks
├── ingest.sh               ← corpus ingestion (run from repo root)
├── backend/                ← Python / FastAPI / MLX
├── frontend/               ← React 18 / Vite / Tailwind
├── evals/                  ← benchmark scripts
├── specs/                  ← architecture decisions, requirements, task breakdowns
├── docs/                   ← implementation reference docs
└── docker/                 ← Docker Compose + Dockerfiles
```

**Technical specs and reference docs:**

| Topic | Document |
|---|---|
| System architecture + ADRs | `specs/architecture/architecture.md` |
| API contract (request/response/SSE) | `specs/architecture/api_contract.md` |
| Corpus parsing rules per book | `specs/architecture/parsing_strategy.md` |
| Product requirements | `specs/requirements/requirements.md` |
| Phase 1 task breakdown | `specs/tasks/phase-1-mvp.md` |
| LLM engine specifics (MLX/CUDA/CPU) | `docs/llm-engine.md` |
| Frontend design tokens | `docs/design-system.md` |

---

## Repository hygiene — mandatory after every change

1. **Delete dead code.** Unused functions, classes, imports, variables — remove them entirely. No comment-outs.
2. **Update deprecated usages.** If a library API changed, fix the call site now. No shims.
3. **Delete orphan files.** If nothing imports a module anymore, delete it.
4. **No stale TODO/FIXME.** Fix it or delete the comment.
5. **Run pre-commit before every commit:**
   ```bash
   pre-commit run --all-files
   ```
   All hooks must pass. Never use `--no-verify`.

---

## Commit format

```
[Phase N] <verb> <what>

[Phase 1] Fix MLX stream_generate sampler parameter
[Phase 1] Remove dead StaticFiles import
[Phase 2] Add TurboQuantMSE cache wrapper
```

---

## Current phase

**Phase 1 — MVP.** Do not implement Phase 2+ features until the Phase 1 gate is met.
Gate criteria and phase breakdown: `specs/tasks/phase-1-mvp.md`.
