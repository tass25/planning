"""Analyze ablation results and produce defense-ready tables + plots.

Usage:
    python scripts/analyze_ablation.py --db ablation.db [--run_id latest] [--plots]

Outputs:
    - Console: stratified hit-rate table
    - docs/ablation_results.md: formatted Markdown with tables
    - docs/ablation_plots/: PNG plots (if --plots)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import structlog

log = structlog.get_logger(__name__)


def analyze(db_path: str, run_id: str | None = None) -> dict:
    """Analyze ablation results. Returns summary dict."""
    conn = duckdb.connect(db_path, read_only=True)

    if run_id is None or run_id == "latest":
        result = conn.execute(
            "SELECT run_id FROM ablation_results ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if not result:
            raise ValueError("No ablation results found")
        run_id = result[0]

    print(f"Analyzing run: {run_id}")

    overall = conn.execute(
        """
        SELECT
            index_type,
            COUNT(*) as n_queries,
            AVG(CAST(hit_at_5 AS DOUBLE)) as hit_rate,
            AVG(reciprocal_rank) as mrr,
            AVG(query_latency_ms) as avg_latency
        FROM ablation_results
        WHERE run_id = ?
        GROUP BY index_type
        ORDER BY index_type
        """,
        [run_id],
    ).fetchall()

    print("\n=== Overall Results ===")
    print(f"{'Index':<10} {'Queries':>8} {'Hit@5':>8} {'MRR':>8} {'Latency':>10}")
    print("-" * 50)
    for row in overall:
        print(f"{row[0]:<10} {row[1]:>8} {row[2]:>8.4f} {row[3]:>8.4f} {row[4]:>10.2f}ms")

    stratified = conn.execute(
        """
        SELECT
            complexity_tier, index_type,
            COUNT(*) as n,
            AVG(CAST(hit_at_5 AS DOUBLE)) as hit_rate,
            AVG(reciprocal_rank) as mrr
        FROM ablation_results
        WHERE run_id = ?
        GROUP BY complexity_tier, index_type
        ORDER BY complexity_tier, index_type
        """,
        [run_id],
    ).fetchall()

    print("\n=== Stratified by Complexity ===")
    print(f"{'Tier':<12} {'Index':<10} {'N':>5} {'Hit@5':>8} {'MRR':>8}")
    print("-" * 50)
    for row in stratified:
        print(f"{row[0]:<12} {row[1]:<10} {row[2]:>5} {row[3]:>8.4f} {row[4]:>8.4f}")

    advantage = conn.execute(
        """
        WITH raptor AS (
            SELECT complexity_tier, AVG(CAST(hit_at_5 AS DOUBLE)) as hit_rate
            FROM ablation_results
            WHERE run_id = ? AND index_type = 'raptor'
            GROUP BY complexity_tier
        ),
        flat AS (
            SELECT complexity_tier, AVG(CAST(hit_at_5 AS DOUBLE)) as hit_rate
            FROM ablation_results
            WHERE run_id = ? AND index_type = 'flat'
            GROUP BY complexity_tier
        )
        SELECT r.complexity_tier,
               r.hit_rate as raptor_hr,
               f.hit_rate as flat_hr,
               r.hit_rate - f.hit_rate as advantage
        FROM raptor r
        JOIN flat f ON r.complexity_tier = f.complexity_tier
        ORDER BY r.complexity_tier
        """,
        [run_id, run_id],
    ).fetchall()

    print("\n=== RAPTOR Advantage ===")
    print(f"{'Tier':<12} {'RAPTOR':>8} {'Flat':>8} {'Delta':>8}")
    print("-" * 45)
    for row in advantage:
        delta_pct = row[3] * 100
        print(f"{row[0]:<12} {row[1]:>8.4f} {row[2]:>8.4f} {delta_pct:>+7.1f}%")

    conn.close()

    return {
        "run_id": run_id,
        "overall": overall,
        "stratified": stratified,
        "advantage": advantage,
    }


def generate_markdown_report(results: dict, output_path: str = "docs/ablation_results.md") -> None:
    """Generate a defense-ready Markdown report."""
    lines = [
        "# Ablation Study: RAPTOR vs Flat Retrieval",
        "",
        "## Study Design",
        "",
        "- **Corpus**: 50 SAS files from benchmark set",
        "- **Queries**: 10 per file = 500 total",
        "- **Stratification**: LOW / MODERATE / HIGH complexity",
        "- **Metric**: hit-rate@5 (binary), MRR (reciprocal rank)",
        "- **Reference**: Sarthi et al., RAPTOR (ICLR 2024)",
        "",
        "## Overall Results",
        "",
        "| Index | Queries | Hit@5 | MRR | Avg Latency |",
        "|-------|--------:|------:|----:|------------:|",
    ]

    for row in results["overall"]:
        lines.append(f"| {row[0]} | {row[1]} | {row[2]:.4f} | {row[3]:.4f} | {row[4]:.2f}ms |")

    lines += [
        "",
        "## Stratified by Complexity",
        "",
        "| Tier | Index | N | Hit@5 | MRR |",
        "|------|-------|--:|------:|----:|",
    ]
    for row in results["stratified"]:
        lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]:.4f} | {row[4]:.4f} |")

    lines += [
        "",
        "## RAPTOR Advantage",
        "",
        "| Tier | RAPTOR | Flat | Advantage | Target >= 10% |",
        "|------|-------:|-----:|----------:|:-------------:|",
    ]
    for row in results["advantage"]:
        delta_pct = row[3] * 100
        check = "YES" if row[3] >= 0.10 else "NO"
        lines.append(f"| {row[0]} | {row[1]:.4f} | {row[2]:.4f} | {delta_pct:+.1f}% | {check} |")

    lines += ["", "---", "", f"> *Ablation run: `{results['run_id']}`*"]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {output_path}")


def generate_plots(db_path: str, run_id: str, output_dir: str = "docs/ablation_plots") -> None:
    """Generate defense-ready plots (requires matplotlib)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    conn = duckdb.connect(db_path, read_only=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    tiers = ["LOW", "MODERATE", "HIGH"]
    raptor_hrs: list[float] = []
    flat_hrs: list[float] = []

    for tier in tiers:
        for idx_type, target_list in [("raptor", raptor_hrs), ("flat", flat_hrs)]:
            result = conn.execute(
                """
                SELECT AVG(CAST(hit_at_5 AS DOUBLE))
                FROM ablation_results
                WHERE run_id = ? AND index_type = ? AND complexity_tier = ?
                """,
                [run_id, idx_type, tier],
            ).fetchone()
            target_list.append(result[0] if result and result[0] else 0)

    x = np.arange(len(tiers))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - width / 2, raptor_hrs, width, label="RAPTOR", color="#2196F3")
    ax.bar(x + width / 2, flat_hrs, width, label="Flat", color="#FF9800")
    ax.set_ylabel("Hit-rate@5")
    ax.set_xlabel("Complexity Tier")
    ax.set_title("RAPTOR vs Flat: Hit-rate@5 by Complexity")
    ax.set_xticks(x)
    ax.set_xticklabels(tiers)
    ax.legend()
    ax.set_ylim(0, 1.0)
    plt.tight_layout()
    plt.savefig(Path(output_dir) / "hit_rate_by_complexity.png", dpi=150)
    plt.close()

    raptor_mrrs = conn.execute(
        "SELECT reciprocal_rank FROM ablation_results WHERE run_id = ? AND index_type = 'raptor'",
        [run_id],
    ).fetchall()
    flat_mrrs = conn.execute(
        "SELECT reciprocal_rank FROM ablation_results WHERE run_id = ? AND index_type = 'flat'",
        [run_id],
    ).fetchall()

    fig, ax = plt.subplots(figsize=(8, 5))
    data = [[r[0] for r in raptor_mrrs], [r[0] for r in flat_mrrs]]
    bp = ax.boxplot(data, labels=["RAPTOR", "Flat"], patch_artist=True)
    bp["boxes"][0].set_facecolor("#2196F3")
    bp["boxes"][1].set_facecolor("#FF9800")
    ax.set_ylabel("Reciprocal Rank")
    ax.set_title("MRR Distribution: RAPTOR vs Flat")
    plt.tight_layout()
    plt.savefig(Path(output_dir) / "mrr_distribution.png", dpi=150)
    plt.close()

    conn.close()
    log.info("ablation_plots_saved", output_dir=output_dir)


def main():
    parser = argparse.ArgumentParser(description="Analyze ablation results")
    parser.add_argument("--db", default="data/ablation.db")
    parser.add_argument("--run_id", default="latest")
    parser.add_argument("--plots", action="store_true", help="Generate plots")
    args = parser.parse_args()

    results = analyze(args.db, args.run_id if args.run_id != "latest" else None)
    generate_markdown_report(results)

    if args.plots:
        generate_plots(args.db, results["run_id"])


if __name__ == "__main__":
    main()
