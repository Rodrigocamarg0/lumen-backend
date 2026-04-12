# AGENTS.md — Evals

> Scope: `evals/`.
> Also read: [`../AGENTS.md`](../AGENTS.md)

---

## Purpose

Validate that changes to the quantizer, KV cache, RAG pipeline, or corpus do not degrade
correctness, memory efficiency, or persona fidelity. Any PR touching those areas must
include a metrics diff from the relevant script.

Pass thresholds and measurement methodology: [`README.md`](./README.md)

---

## Scripts

| Script | Phase | Measures |
|---|---|---|
| `persona_eval.py` | 1+ | RAG Recall@10, citation precision, style drift |
| `turboquant_eval.py` | 2 | Algorithm correctness (30 checks vs paper bounds) |
| `kv_cache_eval.py` | 2 | KV compression ratio, PPL degradation, needle-in-haystack |

---

## Run

```bash
source backend/venv/bin/activate   # from repo root

PYTHONPATH=backend python -m evals.persona_eval      # Phase 1+
PYTHONPATH=backend python -m evals.turboquant_eval   # Phase 2+
PYTHONPATH=backend python -m evals.kv_cache_eval     # Phase 2+
```

---

## Writing new eval scripts

- Runnable as `python -m evals.<name>` with `PYTHONPATH=backend`
- Exit code `0` = all thresholds met; exit code `1` = one or more failed
- Print a machine-readable summary (JSON or structured text) in addition to human output
- No side effects on the production index or model files
- Scripts must be independent — do not import each other

---

## Hygiene

- `print()` is allowed in eval scripts (ruff `T201` suppressed for `evals/`)
- Delete scripts that test removed code paths
- Do not add Phase 2+ scripts before the feature exists
- Keep `README.md` thresholds in sync with what the scripts actually check

---

## Regression workflow

1. Run the relevant eval script before and after your change
2. If a metric degrades: check whether it was intentional (known trade-off)
   - Intentional → update the threshold in the script + document in commit message
   - Unintentional → revert and investigate before resubmitting

---

> See also: [`../AGENTS.md`](../AGENTS.md) · [`README.md`](./README.md) · [`../specs/architecture/architecture.md`](../specs/architecture/architecture.md)
