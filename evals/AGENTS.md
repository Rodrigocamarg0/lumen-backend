# AGENTS.md — Evals

> Scope: everything under `evals/`.
> Also read the root [`../AGENTS.md`](../AGENTS.md) for project-wide rules.

---

## Purpose

The evaluation suite validates that changes to the core pipeline (quantizer, KV cache,
RAG, corpus) do not degrade correctness, memory efficiency, or persona fidelity.

**Rule:** Any PR that modifies the quantizer, rotation matrix logic, RAG embedding schema,
or corpus chunking **must** include a metrics diff from the relevant eval scripts.
Merges are blocked if thresholds degrade.

---

## Scripts

| Script | Phase | What it measures |
|---|---|---|
| `turboquant_eval.py` | 2 | Algorithm correctness against paper bounds (30 checks) |
| `kv_cache_eval.py` | 2 | KV memory compression, PPL degradation, needle-in-haystack |
| `persona_eval.py` | 1+ | RAG Recall@10, citation precision, style drift |

---

## Running evals

```bash
cd /path/to/lumen
source backend/venv/bin/activate

# Phase 1 (available now)
PYTHONPATH=backend python -m evals.persona_eval

# Phase 2+ (requires TurboQuant implementation)
PYTHONPATH=backend python -m evals.turboquant_eval
PYTHONPATH=backend python -m evals.kv_cache_eval
```

---

## Pass thresholds

### `turboquant_eval.py`
| Check | Threshold |
|---|---|
| All 30 algorithm checks | 30/30 pass |
| MSE at 3-bit, d=256 | ≤ 0.035 |
| MSE at 4-bit, d=256 | ≤ 0.011 |

### `kv_cache_eval.py`
| Check | Threshold |
|---|---|
| KV cache compression vs FP16 | ≥ 5× |
| PPL degradation at 3.5-bit | < 1% |
| Needle-in-haystack recall at 4K/16K/64K/128K | > 95% each |

### `persona_eval.py`
| Check | Threshold |
|---|---|
| RAG Recall@10 on Kardec corpus | > 0.90 |
| Citation precision (50 known LdE questions) | > 90% |
| Style drift over 50-turn session | < 5% n-gram deviation |

---

## Writing new eval scripts

- Scripts must be runnable as `python -m evals.<script_name>` with `PYTHONPATH=backend`.
- Output a machine-readable summary (JSON or structured text) in addition to human output.
- Exit code `0` = all thresholds met. Exit code `1` = one or more thresholds failed.
- No side effects on the production index or model files.
- Keep eval scripts independent — they should not import each other.

---

## Hygiene rules for evals

- Eval scripts are allowed to use `print()` (ruff `T201` suppressed for `evals/`).
- Delete eval scripts that test code paths which no longer exist.
- Do not add new eval scripts for Phase 2+ features until the feature exists.
- Keep `README.md` in sync — if a threshold changes, update both the script and the docs.

---

## Regression workflow

When a metric degrades:
1. Check if the change was intentional (e.g., a known trade-off).
2. If intentional: update the threshold in the script and document why in the commit message.
3. If unintentional: revert the change and investigate the root cause before re-submitting.

---

> Also read: [`../AGENTS.md`](../AGENTS.md) · [`../backend/AGENTS.md`](../backend/AGENTS.md)
