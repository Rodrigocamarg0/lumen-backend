"""
KV cache parameter sweep benchmark.

Sends a fixed set of queries against a live Lumen backend under different
KV cache configurations and compares token throughput, RAG latency, and
memory compression. Results are printed as a table and written to
evals/results/bench_<timestamp>.json.

Usage
-----
    # Defaults: sweep bits=[2,3.5,4] × outlier_threshold=[10,15], 5 questions each
    PYTHONPATH=backend python -m evals.kv_cache_bench

    # Custom sweep
    PYTHONPATH=backend python -m evals.kv_cache_bench \\
        --url http://localhost:8000 \\
        --questions 10 \\
        --configs '[{"bits":2,"outlier_threshold":10},{"bits":4,"outlier_threshold":10}]'

    # Disable KV cache as baseline
    PYTHONPATH=backend python -m evals.kv_cache_bench --include-baseline

Exit codes
----------
    0  all configs completed without HTTP errors
    1  server unreachable or one or more configs failed entirely
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from typing import Any
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_URL = "http://localhost:8000"
DEFAULT_QUESTIONS = 5
DEFAULT_CONFIGS: list[dict[str, Any]] = [
    {"enabled": True, "bits": 2.0, "outlier_threshold": 10.0},
    {"enabled": True, "bits": 2.0, "outlier_threshold": 15.0},
    {"enabled": True, "bits": 3.5, "outlier_threshold": 10.0},
    {"enabled": True, "bits": 3.5, "outlier_threshold": 15.0},
    {"enabled": True, "bits": 4.0, "outlier_threshold": 10.0},
]

QUESTION_BANK = Path(__file__).parent / "data" / "lde-50-questions.json"
RESULTS_DIR = Path(__file__).parent / "results"

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _put_json(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def _stream_sse(url: str, body: dict) -> dict[str, Any]:
    """
    POST body to url, consume the SSE stream, and return a dict with keys:
      tokens_generated, tokens_per_second, rag_latency_ms,
      generation_latency_ms, kv_cache_compression_ratio, kv_cache_mb, error
    """
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    result: dict[str, Any] = {"error": None}
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            current_event = ""
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if line.startswith("event:"):
                    current_event = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    payload_str = line[len("data:") :].strip()
                    if payload_str == "[DONE]":
                        break
                    try:
                        payload = json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue
                    if current_event == "stats":
                        # Server wraps stats: {"stats": {...}} — unwrap one level.
                        result.update(payload.get("stats", payload))
                    elif current_event == "error":
                        result["error"] = payload.get("detail", "unknown error")
                        break
    except urllib.error.URLError as exc:
        result["error"] = str(exc)
    return result


# ---------------------------------------------------------------------------
# Config management
# ---------------------------------------------------------------------------


def apply_config(base_url: str, cfg: dict[str, Any]) -> dict:
    return _put_json(f"{base_url}/api/config", cfg)


def read_config(base_url: str) -> dict:
    return _get_json(f"{base_url}/api/config")


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def run_queries(
    base_url: str,
    questions: list[dict],
    persona_id: str = "kardec",
) -> list[dict[str, Any]]:
    results = []
    chat_url = f"{base_url}/api/chat"
    for i, q in enumerate(questions):
        body = {
            "message": q["query"],
            "persona_id": persona_id,
            "options": {"max_new_tokens": 1024, "top_k_chunks": 10, "temperature": 0.0},
        }
        t0 = time.perf_counter()
        row = _stream_sse(chat_url, body)
        wall_ms = int((time.perf_counter() - t0) * 1000)
        row["query"] = q["query"]
        row["wall_ms"] = wall_ms
        row["q_index"] = i
        results.append(row)
        status = "ERR" if row.get("error") else "ok"
        tps = row.get("tokens_per_second", 0)
        rag = row.get("rag_latency_ms", 0)
        print(f"    [{i + 1}/{len(questions)}] {status}  {tps:.1f} tok/s  RAG {rag}ms", flush=True)
    return results


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in results if not r.get("error")]
    if not ok:
        return {"n": 0, "error_rate": 1.0}

    def mean(key: str) -> float:
        vals = [r[key] for r in ok if key in r]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    return {
        "n": len(ok),
        "error_rate": round((len(results) - len(ok)) / len(results), 3),
        "tokens_per_second_mean": mean("tokens_per_second"),
        "rag_latency_ms_mean": mean("rag_latency_ms"),
        "generation_latency_ms_mean": mean("generation_latency_ms"),
        "tokens_generated_mean": mean("tokens_generated"),
        "kv_cache_compression_ratio_mean": mean("kv_cache_compression_ratio"),
        "kv_cache_mb_mean": mean("kv_cache_mb"),
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _config_label(cfg: dict[str, Any]) -> str:
    if not cfg.get("enabled", True):
        return "baseline (no cache)"
    return f"bits={cfg.get('bits', '?')}  threshold={cfg.get('outlier_threshold', '?')}"


def print_table(sweep_results: list[dict[str, Any]]) -> None:
    col_w = 26
    num_w = 10
    headers = ["config", "tok/s", "RAG ms", "gen ms", "tokens", "ratio", "MB"]
    widths = [col_w] + [num_w] * (len(headers) - 1)
    sep = "  ".join("-" * w for w in widths)
    header = "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))

    print()
    print("=== KV Cache Benchmark Results ===")
    print(sep)
    print(header)
    print(sep)
    for entry in sweep_results:
        label = _config_label(entry["config"])[:col_w]
        agg = entry["aggregate"]
        if agg["n"] == 0:
            row = [label] + ["FAILED"] + [""] * (len(headers) - 2)
        else:
            ratio = agg.get("kv_cache_compression_ratio_mean") or 0
            row = [
                label,
                f"{agg['tokens_per_second_mean']:.1f}",
                f"{agg['rag_latency_ms_mean']:.0f}",
                f"{agg['generation_latency_ms_mean']:.0f}",
                f"{agg['tokens_generated_mean']:.0f}",
                f"{ratio:.2f}x" if ratio else "—",
                f"{agg['kv_cache_mb_mean']:.2f}",
            ]
        print("  ".join(str(v).ljust(w) for v, w in zip(row, widths, strict=True)))
    print(sep)
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="KV cache parameter sweep benchmark")
    parser.add_argument("--url", default=DEFAULT_URL, help="Backend base URL")
    parser.add_argument(
        "--questions",
        type=int,
        default=DEFAULT_QUESTIONS,
        help="Number of questions per config",
    )
    parser.add_argument(
        "--configs",
        type=str,
        default=None,
        help="JSON array of config dicts (bits, outlier_threshold, enabled)",
    )
    parser.add_argument(
        "--include-baseline",
        action="store_true",
        help="Prepend a run with USE_TURBOQUANT_CACHE=false",
    )
    parser.add_argument("--persona", default="kardec")
    args = parser.parse_args()

    # Health check
    try:
        health = _get_json(f"{args.url}/api/health")
    except Exception as exc:
        print(f"ERROR: cannot reach server at {args.url}: {exc}", file=sys.stderr)
        return 1

    if not health.get("model_loaded"):
        print("ERROR: model is not loaded yet (/api/health model_loaded=false)", file=sys.stderr)
        return 1
    if not health.get("index_loaded"):
        print("ERROR: index is not loaded yet (/api/health index_loaded=false)", file=sys.stderr)
        return 1

    print(f"Server OK  model={health.get('model_loaded')}  index={health.get('index_loaded')}")

    # Load questions
    with open(QUESTION_BANK) as f:
        all_questions = json.load(f)
    questions = all_questions[: args.questions]
    print(f"Using {len(questions)} questions from {QUESTION_BANK.name}\n")

    # Build config sweep
    configs: list[dict[str, Any]] = (
        json.loads(args.configs) if args.configs else list(DEFAULT_CONFIGS)
    )
    if args.include_baseline:
        configs = [{"enabled": False}, *configs]

    sweep_results: list[dict[str, Any]] = []
    failed = False

    for cfg in configs:
        label = _config_label(cfg)
        print(f"— Config: {label}")

        try:
            effective = apply_config(args.url, cfg)
            print(f"  Applied: {effective}")
        except Exception as exc:
            print(f"  ERROR applying config: {exc}", file=sys.stderr)
            failed = True
            sweep_results.append(
                {"config": cfg, "aggregate": {"n": 0, "error_rate": 1.0}, "rows": []}
            )
            continue

        rows = run_queries(args.url, questions, persona_id=args.persona)
        agg = aggregate(rows)
        sweep_results.append(
            {"config": cfg, "effective_config": effective, "aggregate": agg, "rows": rows}
        )

        if agg["error_rate"] > 0:
            failed = True

    print_table(sweep_results)

    # Save results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"bench_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(
            {
                "timestamp": ts,
                "url": args.url,
                "questions_used": len(questions),
                "sweep": sweep_results,
            },
            f,
            indent=2,
        )
    print(f"Results written to {out_path}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
