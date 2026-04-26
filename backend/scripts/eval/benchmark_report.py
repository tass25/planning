"""Benchmark Report Generator — tableau récapitulatif complet.

Reads benchmark_results.json + all benchmark_detail_*.jsonl files
and produces a comprehensive comparison table covering:
  - Model identity (name, provider, params, architecture)
  - Quality metrics (confidence, acceptance rate, issues)
  - Performance metrics (latency per prompt, tokens, lines)
  - Cost estimation (tokens × rate)
  - Per-category breakdown
  - Pros / Cons summary

Usage::

    python scripts/benchmark_report.py
    python scripts/benchmark_report.py --output report.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Model metadata registry (architecture, params, context, notes)
# ---------------------------------------------------------------------------
MODEL_META: dict[str, dict] = {
    "mistralai/mistral-medium-3-instruct": {
        "params": "~22B active (MoE)",
        "architecture": "Transformer MoE",
        "context_k": 128,
        "provider_tag": "Mistral AI / NVIDIA NIM",
        "free_tier": True,
        "notes": "Multimodal, strong at instruction following & code",
        "pros": ["Fast verifier response", "High acceptance rate", "Reliable JSON output"],
        "cons": ["Slow Prompt B (~30-70s)", "Single key = one rate-limit bucket"],
    },
    "moonshotai/kimi-k2-instruct": {
        "params": "1T MoE (active ~32B est.)",
        "architecture": "MoE Transformer",
        "context_k": 128,
        "provider_tag": "Moonshot AI / NVIDIA NIM",
        "free_tier": True,
        "notes": "Very large capacity model, strong reasoning & agentic tasks",
        "pros": ["Massive parameter count", "Strong reasoning"],
        "cons": ["Potentially slower inference", "Less tested on SAS"],
    },
    "qwen/qwen3.5-122b-a10b": {
        "params": "122B MoE (10B active)",
        "architecture": "MoE Transformer",
        "context_k": 32,
        "provider_tag": "Qwen / NVIDIA NIM",
        "free_tier": True,
        "notes": "Code + tool-calling specialist, low active params = fast",
        "pros": ["Low active params -> fast", "Code-optimized"],
        "cons": ["Tight free-tier token budget", "429 on bulk requests"],
    },
    "mistralai/devstral-2-123b-instruct-2512": {
        "params": "123B",
        "architecture": "Dense Transformer",
        "context_k": 256,
        "provider_tag": "Mistral AI / NVIDIA NIM",
        "free_tier": True,
        "notes": "Coding specialist, 256K context",
        "pros": ["Long context", "Code-first design"],
        "cons": ["Server errors during test period", "Heavy model"],
    },
    "llama-3.3-70b-versatile": {
        "params": "70B",
        "architecture": "Dense Transformer",
        "context_k": 128,
        "provider_tag": "Meta / Groq",
        "free_tier": True,
        "notes": "Used as verifier — fast Groq inference",
        "pros": ["<1s verification latency on Groq", "Reliable JSON mode"],
        "cons": ["Free tier RPM limit", "Needs 3 keys for bulk runs"],
    },
    "meta/llama-4-maverick-17b-128e-instruct": {
        "params": "17B × 128 experts MoE",
        "architecture": "MoE Transformer",
        "context_k": 1000,
        "provider_tag": "Meta / NVIDIA NIM",
        "free_tier": True,
        "notes": "Used as fallback verifier on NVIDIA NIM",
        "pros": ["1M context", "Free endpoint"],
        "cons": ["Less powerful than Groq llama-3.3-70b for verification"],
    },
}

# Estimated cost per 1K tokens (free tier = $0, noted for reference)
COST_PER_1K = {
    "mistralai/mistral-medium-3-instruct": 0.0,
    "moonshotai/kimi-k2-instruct": 0.0,
    "qwen/qwen3.5-122b-a10b": 0.0,
    "llama-3.3-70b-versatile": 0.0,
    "meta/llama-4-maverick-17b-128e-instruct": 0.0,
}


def load_data(kb_dir: str = "knowledge_base") -> tuple[list[dict], list[dict]]:
    """Load benchmark_results.json and all detail JSONL files."""
    runs_path = os.path.join(kb_dir, "benchmark_results.json")
    if not os.path.exists(runs_path):
        print(f"ERROR: {runs_path} not found. Run generate_kb_pairs.py first.")
        sys.exit(1)

    with open(runs_path) as f:
        runs = json.load(f)["runs"]

    # Merge all detail rows
    detail_rows: list[dict] = []
    for path in Path(kb_dir).glob("benchmark_detail_*.jsonl"):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    detail_rows.append(json.loads(line))

    return runs, detail_rows


def _bar(value: float, max_val: float = 1.0, width: int = 20) -> str:
    filled = int((value / max(max_val, 1e-9)) * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def print_report(runs: list[dict], detail_rows: list[dict], out_lines: list[str]) -> None:
    def p(*args):
        line = " ".join(str(a) for a in args)
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode("ascii", errors="replace").decode())
        out_lines.append(line)

    p("=" * 110)
    p("  TABLEAU RECAPITULATIF — KB GENERATION BENCHMARK")
    p("  Codara SAS->Python Accelerator | Knowledge Base Quality Assessment")
    p("=" * 110)

    # ── 1. Run summary table ──────────────────────────────────────────────
    p("\n[1] RUN SUMMARY")
    p("-" * 110)
    header = (
        f"{'Run':<10} {'Provider':<10} {'Model':<42} {'Ver':>4} {'Gen':>4} "
        f"{'Acc%':>5} {'AvgConf':>8} {'MinConf':>8} {'MaxConf':>8} {'AvgLat':>8}"
    )
    p(header)
    p("-" * 110)

    # Only show runs with verified > 0
    active_runs = [r for r in runs if r.get("verified", 0) > 0]
    for r in active_runs:
        model = r.get("gen_model", "?")
        model_short = model.split("/")[-1][:40]
        p(
            f"{r.get('run_id', '?'):<10} "
            f"{r.get('provider', '?'):<10} "
            f"{model_short:<42} "
            f"{r.get('verified', 0):>4} "
            f"{r.get('generated', 0):>4} "
            f"{r.get('acceptance_rate', 0) * 100:>4.0f}% "
            f"{r.get('avg_confidence', 0):>8.3f} "
            f"{r.get('min_confidence', r.get('avg_confidence', 0)):>8.3f} "
            f"{r.get('max_confidence', r.get('avg_confidence', 0)):>8.3f} "
            f"{r.get('avg_latency_s', 0):>7.1f}s"
        )
    p("-" * 110)

    # ── 2. Performance breakdown ──────────────────────────────────────────
    p("\n[2] PERFORMANCE BREAKDOWN (avg per pair)")
    p("-" * 110)
    p(
        f"{'Model':<42} {'PromptA':>9} {'PromptB':>9} {'PromptC':>9} {'Total':>8} {'SAS lines':>10} {'PY lines':>9} {'Tokens':>8}"
    )
    p("-" * 110)
    for r in active_runs:
        model = r.get("gen_model", "?").split("/")[-1][:40]
        p(
            f"{model:<42} "
            f"{r.get('avg_t_prompt_a', 0):>8.1f}s "
            f"{r.get('avg_t_prompt_b', 0):>8.1f}s "
            f"{r.get('avg_t_prompt_c', 0):>8.2f}s "
            f"{r.get('avg_latency_s', 0):>7.1f}s "
            f"{r.get('avg_sas_lines', 0):>10.1f} "
            f"{r.get('avg_py_lines', 0):>9.1f} "
            f"{int(r.get('avg_tokens_est', 0)):>8}"
        )

    # ── 3. Per-category quality (from detail rows) ────────────────────────
    if detail_rows:
        p("\n[3] PER-CATEGORY QUALITY (from verified pairs)")
        p("-" * 110)

        # Group by (run_id, category)
        by_run_cat: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        for row in detail_rows:
            by_run_cat[row["run_id"]][row["category"]].append(row)

        all_cats = sorted({r["category"] for r in detail_rows})
        run_ids = list({r["run_id"] for r in detail_rows})

        # Header
        run_labels = [r.get("run_id", "?")[:8] for r in active_runs if r.get("run_id") in run_ids]
        p(f"{'Category':<30} " + "  ".join(f"{'[' + rid + ']':>14}" for rid in run_labels))
        p(f"{'':30} " + "  ".join(f"{'conf / lat':>14}" for _ in run_labels))
        p("-" * 110)

        for cat in all_cats:
            row_parts = []
            for rid in run_labels:
                rows = by_run_cat[rid].get(cat, [])
                if rows:
                    avg_conf = sum(r["confidence"] for r in rows) / len(rows)
                    avg_lat = sum(r["t_total_s"] for r in rows if r.get("t_total_s")) / max(
                        len(rows), 1
                    )
                    row_parts.append(f"{avg_conf:.2f} / {avg_lat:4.0f}s")
                else:
                    row_parts.append("      --      ")
            p(f"{cat:<30} " + "  ".join(f"{v:>14}" for v in row_parts))

    # ── 4. Failure-mode coverage ──────────────────────────────────────────
    if detail_rows:
        p("\n[4] FAILURE-MODE COVERAGE")
        p("-" * 80)
        fm_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for row in detail_rows:
            fm = row.get("failure_mode", "none") or "none"
            fm_counts[row["run_id"]][fm] += 1

        all_fms = sorted({r.get("failure_mode", "none") or "none" for r in detail_rows})
        run_ids_det = list({r["run_id"] for r in detail_rows})
        p(f"{'Failure Mode':<35} " + "  ".join(f"{rid[:8]:>8}" for rid in run_ids_det))
        p("-" * 80)
        for fm in all_fms:
            counts = [str(fm_counts[rid].get(fm, 0)) for rid in run_ids_det]
            p(f"{fm:<35} " + "  ".join(f"{c:>8}" for c in counts))

    # ── 5. Model info + pros/cons ─────────────────────────────────────────
    p("\n[5] MODEL PROFILES")
    p("=" * 110)
    seen_models = {r.get("gen_model") for r in active_runs}
    for model in seen_models:
        meta = MODEL_META.get(model, {})
        model.split("/")[-1]
        p(f"\n  MODEL : {model}")
        p(
            f"  Params: {meta.get('params', 'unknown'):<25}  Architecture: {meta.get('architecture', '?')}"
        )
        p(
            f"  Context: {meta.get('context_k', '?')}K tokens        Provider: {meta.get('provider_tag', '?')}"
        )
        p(f"  Notes : {meta.get('notes', '')}")
        pros = meta.get("pros", [])
        cons = meta.get("cons", [])
        if pros:
            p("  PROS  : " + " | ".join(pros))
        if cons:
            p("  CONS  : " + " | ".join(cons))

        # Find matching run stats
        run_stats = [r for r in active_runs if r.get("gen_model") == model]
        if run_stats:
            best = max(run_stats, key=lambda x: x.get("verified", 0))
            p(
                f"  BEST RUN [{best.get('run_id', '')}]: "
                f"{best.get('verified', 0)} pairs | "
                f"acc={best.get('acceptance_rate', 0) * 100:.0f}% | "
                f"conf={best.get('avg_confidence', 0):.3f} | "
                f"lat={best.get('avg_latency_s', 0):.1f}s/pair"
            )
        p("  " + "-" * 80)

    # ── 6. Head-to-head comparison ────────────────────────────────────────
    p("\n[6] HEAD-TO-HEAD COMPARISON")
    p("=" * 110)
    p(
        f"{'Metric':<35} "
        + "  ".join(f"{r.get('gen_model', '?').split('/')[-1][:25]:>27}" for r in active_runs)
    )
    p("-" * 110)

    metrics_map = [
        ("Verified pairs", lambda r: str(r.get("verified", 0))),
        ("Acceptance rate", lambda r: f"{r.get('acceptance_rate', 0) * 100:.0f}%"),
        ("Avg confidence", lambda r: f"{r.get('avg_confidence', 0):.3f}"),
        ("Min confidence", lambda r: f"{r.get('min_confidence', r.get('avg_confidence', 0)):.3f}"),
        ("Avg total latency", lambda r: f"{r.get('avg_latency_s', 0):.1f}s"),
        ("Avg Prompt A (SAS gen)", lambda r: f"{r.get('avg_t_prompt_a', 0):.1f}s"),
        ("Avg Prompt B (PY conv)", lambda r: f"{r.get('avg_t_prompt_b', 0):.1f}s"),
        ("Avg Prompt C (verify)", lambda r: f"{r.get('avg_t_prompt_c', 0):.2f}s"),
        ("Avg SAS lines", lambda r: f"{r.get('avg_sas_lines', 0):.0f}"),
        ("Avg Python lines", lambda r: f"{r.get('avg_py_lines', 0):.0f}"),
        ("Avg tokens (est)", lambda r: f"{int(r.get('avg_tokens_est', 0))}"),
        ("Model params", lambda r: MODEL_META.get(r.get("gen_model", ""), {}).get("params", "?")),
        (
            "Context window",
            lambda r: f"{MODEL_META.get(r.get('gen_model', ''), {}).get('context_k', '?')}K",
        ),
        (
            "Free tier",
            lambda r: (
                "Yes" if MODEL_META.get(r.get("gen_model", ""), {}).get("free_tier") else "No"
            ),
        ),
    ]

    for label, fn in metrics_map:
        vals = [fn(r) for r in active_runs]
        p(f"{label:<35} " + "  ".join(f"{v:>27}" for v in vals))

    # ── 7. Recommendation ────────────────────────────────────────────────
    p("\n[7] RECOMMENDATION")
    p("=" * 110)
    if len(active_runs) >= 2:
        best_quality = max(active_runs, key=lambda r: r.get("avg_confidence", 0))
        best_speed = min(active_runs, key=lambda r: r.get("avg_latency_s", 999))
        best_yield = max(active_runs, key=lambda r: r.get("acceptance_rate", 0))
        p(
            f"  Best quality (confidence) : {best_quality.get('gen_model', '?')}  [{best_quality.get('avg_confidence', 0):.3f}]"
        )
        p(
            f"  Best speed  (latency)     : {best_speed.get('gen_model', '?')}  [{best_speed.get('avg_latency_s', 0):.1f}s/pair]"
        )
        p(
            f"  Best yield  (acceptance%) : {best_yield.get('gen_model', '?')}  [{best_yield.get('acceptance_rate', 0) * 100:.0f}%]"
        )
    else:
        p("  Only one model benchmarked so far. Run Kimi to enable comparison.")

    p("\n  Verifier used: Groq llama-3.3-70b-versatile")
    p("  Threshold    : 0.65 confidence required for pair acceptance")
    p("  Embedding    : nomic-ai/nomic-embed-text-v1.5 (768-dim, CPU)")
    p("\n" + "=" * 110)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-dir", default="knowledge_base")
    parser.add_argument("--output", default=None, help="Save report to file (e.g. report.txt)")
    args = parser.parse_args()

    runs, detail_rows = load_data(args.kb_dir)
    out_lines: list[str] = []
    print_report(runs, detail_rows, out_lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write("\n".join(out_lines))
        print(f"\nReport saved to: {args.output}")


if __name__ == "__main__":
    main()
