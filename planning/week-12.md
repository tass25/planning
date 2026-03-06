# Week 12: Ablation Study — RAPTOR vs Flat Retrieval

> **Priority**: P2  
> **Branch**: `week-12`  
> **Layer**: Evaluation  
> **Prerequisite**: Week 11 complete (full pipeline running end-to-end, KB ≥ 330 pairs)  

---

## 🎯 Goal

Design and execute a rigorous ablation study comparing RAPTOR hierarchical retrieval against flat (non-hierarchical) retrieval. The study must produce quantitative evidence that RAPTOR improves retrieval quality — or document an honest negative result. This is a core defense deliverable: the jury will evaluate whether the RAPTOR adaptation from Sarthi et al. (ICLR 2024) is justified.

---

## Study Design

### Experimental Setup

```
50 SAS files × 10 queries per file = 500 query-retrieval pairs
                    ↓
         Two index configurations:
         ┌────────────────────────┐
         │  RAPTOR (hierarchical) │ ← GMM clusters + summaries
         │  Flat (baseline)       │ ← raw partitions only
         └────────────────────────┘
                    ↓
         Metrics per query:
         - hit@5 (binary: correct KB pair in top-5 results?)
         - reciprocal_rank (1/rank of first correct result)
         - query_latency_ms
                    ↓
         Stratification by:
         - complexity_tier (LOW / MODERATE / HIGH)
         - depth_level (0=leaf, 1=L1, 2=L2, 3=root)
```

### Key Hypotheses

| # | Hypothesis | Expected Outcome |
|---|-----------|-----------------|
| H1 | RAPTOR hit-rate@5 > 0.82 overall | Match paper claims on code domain |
| H2 | RAPTOR advantage ≥ 10% on MODERATE/HIGH | Hierarchical clustering benefits complex blocks |
| H3 | RAPTOR advantage ≈ 0% on LOW | Simple blocks don't benefit from hierarchy |
| H4 | Query latency overhead < 50ms | Extra hops through tree don't kill performance |

---

## Task 1: Build the Flat Index Baseline

**File**: `partition/evaluation/flat_index.py`

```python
"""
Flat Index Baseline — for ablation comparison.

Creates a LanceDB table with only leaf-level embeddings (no hierarchical
cluster summaries). This represents the "no RAPTOR" baseline — standard
cosine-similarity retrieval on raw partition embeddings.
"""

import lancedb
import pyarrow as pa
import structlog

log = structlog.get_logger(__name__)

FLAT_SCHEMA = pa.schema([
    pa.field("node_id", pa.string()),
    pa.field("file_id", pa.string()),
    pa.field("partition_id", pa.string()),
    pa.field("partition_type", pa.string()),
    pa.field("complexity_tier", pa.string()),
    pa.field("summary", pa.string()),
    pa.field("embedding", pa.list_(pa.float32(), 768)),
    pa.field("raw_code_snippet", pa.string()),
])


def build_flat_index(
    db_path: str,
    table_name: str = "flat_nodes",
    raptor_table_name: str = "raptor_nodes",
) -> None:
    """
    Build a flat index from existing RAPTOR nodes by keeping ONLY level-0 (leaf) nodes.
    
    This ensures both indexes have the same leaf content — the only
    difference is that RAPTOR has cluster and root nodes as well.
    """
    db = lancedb.connect(db_path)
    raptor_table = db.open_table(raptor_table_name)

    # Get all leaf nodes (level == 0)
    df = raptor_table.to_pandas()
    leaves = df[df["level"] == 0].copy()

    log.info(
        "flat_index_built",
        total_raptor_nodes=len(df),
        leaf_nodes=len(leaves),
        dropped_cluster_nodes=len(df) - len(leaves),
    )

    # Create flat table
    if table_name in db.table_names():
        db.drop_table(table_name)

    db.create_table(table_name, data=leaves)

    # Build IVF index
    flat_table = db.open_table(table_name)
    flat_table.create_index(
        metric="cosine",
        num_partitions=32,
        num_sub_vectors=48,
    )

    log.info("flat_index_ivf_created", table=table_name, partitions=32)


def query_flat(
    db_path: str,
    query_embedding: list[float],
    k: int = 5,
    table_name: str = "flat_nodes",
    filter_expr: str | None = None,
) -> list[dict]:
    """
    Query the flat index. Returns top-k results.
    """
    db = lancedb.connect(db_path)
    table = db.open_table(table_name)

    q = table.search(query_embedding).limit(k)
    if filter_expr:
        q = q.where(filter_expr)

    results = q.to_pandas().to_dict("records")
    return results
```

---

## Task 2: Query Generation (50 files × 10 queries)

**File**: `partition/evaluation/query_generator.py`

```python
"""
Query Generator — Generate 500 ablation queries.

For each of the 50 benchmark files:
  - Extract 10 partitions (stratified by complexity)
  - Generate a natural-language query that should retrieve a relevant KB pair
  - Ground truth: the partition_type + expected KB category

Query format:
  "Convert this SAS DATA step with RETAIN to Python using cumulative sum"
  → expected: DATA_STEP_RETAIN category, RETAIN failure mode
"""

import json
import random
from pathlib import Path
from typing import Optional
from uuid import uuid4

import structlog

log = structlog.get_logger(__name__)

# Query templates per partition type
QUERY_TEMPLATES = {
    "DATA_STEP_BASIC": [
        "Convert SAS DATA step with assignment and keep/drop to Python pandas",
        "Translate SAS DATA step if/else logic to Python",
    ],
    "DATA_STEP_MERGE": [
        "Convert SAS MERGE BY statement to Python pandas merge",
        "Translate SAS one-to-many merge to Python",
    ],
    "DATA_STEP_RETAIN": [
        "Convert SAS RETAIN with running total to Python cumulative sum",
        "Translate SAS lag pattern to Python shift operation",
    ],
    "DATA_STEP_ARRAY": [
        "Convert SAS ARRAY with DO OVER to Python list comprehension",
        "Translate SAS multi-dimensional array to Python numpy",
    ],
    "DATA_STEP_FIRST_LAST": [
        "Convert SAS FIRST.var / LAST.var BY-group processing to Python groupby",
        "Translate SAS FIRST/LAST flags to pandas groupby head/tail",
    ],
    "DATE_ARITHMETIC": [
        "Convert SAS INTNX INTCK date functions to Python pandas DateOffset",
        "Translate SAS MDY TODAY date creation to Python datetime",
    ],
    "PROC_SQL": [
        "Convert SAS PROC SQL with JOIN and subquery to Python pandas",
        "Translate SAS PROC SQL GROUP BY HAVING to Python",
    ],
    "PROC_MEANS": [
        "Convert SAS PROC MEANS with CLASS VAR OUTPUT OUT to Python groupby agg",
        "Translate SAS PROC MEANS NWAY to Python pandas",
    ],
    "PROC_FREQ": [
        "Convert SAS PROC FREQ cross-tabulation to Python pandas crosstab",
        "Translate SAS PROC FREQ chi-square to Python scipy",
    ],
    "MACRO_BASIC": [
        "Convert SAS %MACRO %MEND %LET to Python function",
        "Translate SAS macro parameters to Python function arguments",
    ],
    "MACRO_CONDITIONAL": [
        "Convert SAS %IF %THEN %ELSE to Python if/else",
        "Translate nested SAS %DO %END to Python loop",
    ],
    "PROC_SORT": [
        "Convert SAS PROC SORT BY NODUPKEY to Python sort_values drop_duplicates",
        "Translate SAS PROC SORT descending to Python pandas",
    ],
    "PROC_REG_LOGISTIC": [
        "Convert SAS PROC REG MODEL to Python statsmodels OLS",
        "Translate SAS PROC LOGISTIC to Python sklearn LogisticRegression",
    ],
    "PROC_IMPORT_EXPORT": [
        "Convert SAS PROC IMPORT DBMS CSV to Python pandas read_csv",
        "Translate SAS INFILE INPUT to Python file reading",
    ],
    "MISSING_VALUE_HANDLING": [
        "Convert SAS NMISS CMISS missing value handling to Python isna",
        "Translate SAS missing value dot comparison to Python NaN check",
    ],
}


def generate_queries(
    partitions: list[dict],
    n_per_file: int = 10,
    seed: int = 42,
) -> list[dict]:
    """
    Generate ablation queries from partition data.
    
    Args:
        partitions: List of PartitionIR dicts with partition_type, complexity_tier.
        n_per_file: Number of queries per file.
        seed: Random seed for reproducibility.
    
    Returns:
        List of query dicts with query_text, expected_type, complexity_tier.
    """
    rng = random.Random(seed)
    queries = []

    # Group by file
    by_file: dict[str, list[dict]] = {}
    for p in partitions:
        fid = p.get("source_file_id", "unknown")
        by_file.setdefault(fid, []).append(p)

    for file_id, file_parts in by_file.items():
        # Stratified sample: try to get LOW, MODERATE, HIGH
        by_tier = {"LOW": [], "MODERATE": [], "HIGH": []}
        for p in file_parts:
            tier = p.get("complexity_tier", "LOW")
            if tier in by_tier:
                by_tier[tier].append(p)

        selected = []
        # Take proportional samples
        for tier, parts in by_tier.items():
            n_take = max(1, round(n_per_file * len(parts) / max(len(file_parts), 1)))
            selected.extend(rng.sample(parts, min(n_take, len(parts))))

        # Pad to n_per_file if needed
        while len(selected) < n_per_file and file_parts:
            selected.append(rng.choice(file_parts))
        selected = selected[:n_per_file]

        for p in selected:
            ptype = p.get("partition_type", "DATA_STEP_BASIC")
            templates = QUERY_TEMPLATES.get(ptype, ["Convert this SAS code to Python"])
            query_text = rng.choice(templates)

            queries.append({
                "query_id": str(uuid4()),
                "file_id": file_id,
                "partition_id": p.get("partition_id", ""),
                "query_text": query_text,
                "expected_partition_type": ptype,
                "complexity_tier": p.get("complexity_tier", "LOW"),
                "expected_category": ptype,  # category in KB
            })

    log.info("queries_generated", total=len(queries))
    return queries
```

---

## Task 3: Ablation Runner

**File**: `partition/evaluation/ablation_runner.py`

```python
"""
Ablation Runner — Execute RAPTOR vs Flat retrieval comparison.

For each query:
  1. Embed the query text
  2. Search RAPTOR index → top-5 results
  3. Search Flat index → top-5 results
  4. Compare against ground truth
  5. Record metrics to DuckDB ablation_results
"""

import time
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import duckdb
import lancedb
import structlog

log = structlog.get_logger(__name__)


class AblationRunner:
    """
    Runs the RAPTOR vs Flat ablation study.
    """

    def __init__(
        self,
        lancedb_path: str,
        duckdb_path: str,
        embed_fn,
        raptor_table: str = "raptor_nodes",
        flat_table: str = "flat_nodes",
        k: int = 5,
    ):
        """
        Args:
            lancedb_path: Path to LanceDB storage.
            duckdb_path: Path to DuckDB analytics database.
            embed_fn: callable(text) → list[float] (768-dim Nomic embedding).
            raptor_table: LanceDB table name for RAPTOR index.
            flat_table: LanceDB table name for flat index.
            k: Top-k retrieval count.
        """
        self.db = lancedb.connect(lancedb_path)
        self.duckdb_conn = duckdb.connect(duckdb_path)
        self.embed_fn = embed_fn
        self.raptor_table = raptor_table
        self.flat_table = flat_table
        self.k = k
        self.run_id = str(uuid4())

    def run(self, queries: list[dict]) -> dict:
        """
        Execute the full ablation study.

        Args:
            queries: list of query dicts from query_generator.

        Returns:
            Summary dict with aggregate metrics.
        """
        log.info("ablation_started", run_id=self.run_id, n_queries=len(queries))

        results = {"raptor": [], "flat": []}

        for i, query in enumerate(queries):
            query_text = query["query_text"]
            expected_type = query["expected_partition_type"]
            complexity = query["complexity_tier"]

            # Embed the query
            embedding = self.embed_fn(query_text)

            # ---- RAPTOR retrieval ----
            raptor_result = self._search_and_evaluate(
                table_name=self.raptor_table,
                index_type="raptor",
                embedding=embedding,
                expected_type=expected_type,
                query=query,
                complexity=complexity,
            )
            results["raptor"].append(raptor_result)

            # ---- Flat retrieval ----
            flat_result = self._search_and_evaluate(
                table_name=self.flat_table,
                index_type="flat",
                embedding=embedding,
                expected_type=expected_type,
                query=query,
                complexity=complexity,
            )
            results["flat"].append(flat_result)

            if (i + 1) % 50 == 0:
                log.info("ablation_progress", completed=i + 1, total=len(queries))

        # Compute aggregate metrics
        summary = self._compute_summary(results)
        log.info("ablation_complete", **summary)
        return summary

    def _search_and_evaluate(
        self,
        table_name: str,
        index_type: str,
        embedding: list[float],
        expected_type: str,
        query: dict,
        complexity: str,
    ) -> dict:
        """
        Search one index and evaluate the results.
        """
        table = self.db.open_table(table_name)

        start = time.perf_counter()
        hits = table.search(embedding).limit(self.k).to_pandas()
        latency_ms = (time.perf_counter() - start) * 1000

        # Evaluate: did the correct partition_type appear in top-k?
        hit_types = hits["partition_type"].tolist() if "partition_type" in hits.columns else []
        hit_at_k = expected_type in hit_types

        # Reciprocal rank
        rr = 0.0
        for rank, ht in enumerate(hit_types, 1):
            if ht == expected_type:
                rr = 1.0 / rank
                break

        result = {
            "run_id": self.run_id,
            "file_id": query["file_id"],
            "query_id": query["query_id"],
            "index_type": index_type,
            "hit_at_5": hit_at_k,
            "reciprocal_rank": rr,
            "query_latency_ms": latency_ms,
            "complexity_tier": complexity,
            "depth_level": 0,  # leaves for flat, mixed for RAPTOR
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Write to DuckDB
        self._write_result(result)
        return result

    def _write_result(self, result: dict) -> None:
        """Insert one ablation result into DuckDB."""
        self.duckdb_conn.execute(
            """
            INSERT INTO ablation_results
            (run_id, file_id, query_id, index_type,
             hit_at_5, reciprocal_rank, query_latency_ms,
             complexity_tier, depth_level, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                result["run_id"],
                result["file_id"],
                result["query_id"],
                result["index_type"],
                result["hit_at_5"],
                result["reciprocal_rank"],
                result["query_latency_ms"],
                result["complexity_tier"],
                result["depth_level"],
                result["created_at"],
            ],
        )

    def _compute_summary(self, results: dict) -> dict:
        """Compute aggregate metrics from all results."""
        summary = {}

        for idx_type in ("raptor", "flat"):
            items = results[idx_type]
            n = len(items)
            if n == 0:
                continue

            hit_rate = sum(1 for r in items if r["hit_at_5"]) / n
            mrr = sum(r["reciprocal_rank"] for r in items) / n
            avg_latency = sum(r["query_latency_ms"] for r in items) / n

            # Stratified by complexity
            by_tier = {}
            for tier in ("LOW", "MODERATE", "HIGH"):
                tier_items = [r for r in items if r["complexity_tier"] == tier]
                if tier_items:
                    by_tier[tier] = {
                        "hit_rate": sum(1 for r in tier_items if r["hit_at_5"]) / len(tier_items),
                        "mrr": sum(r["reciprocal_rank"] for r in tier_items) / len(tier_items),
                        "count": len(tier_items),
                    }

            summary[idx_type] = {
                "hit_rate_at_5": round(hit_rate, 4),
                "mrr": round(mrr, 4),
                "avg_latency_ms": round(avg_latency, 2),
                "n_queries": n,
                "by_complexity": by_tier,
            }

        # Compute advantage
        if "raptor" in summary and "flat" in summary:
            summary["advantage"] = {
                "hit_rate_delta": round(
                    summary["raptor"]["hit_rate_at_5"] - summary["flat"]["hit_rate_at_5"], 4
                ),
                "mrr_delta": round(
                    summary["raptor"]["mrr"] - summary["flat"]["mrr"], 4
                ),
            }
            # Per-tier advantage
            for tier in ("LOW", "MODERATE", "HIGH"):
                r_tier = summary["raptor"]["by_complexity"].get(tier, {})
                f_tier = summary["flat"]["by_complexity"].get(tier, {})
                if r_tier and f_tier:
                    summary["advantage"][f"{tier}_hit_rate_delta"] = round(
                        r_tier["hit_rate"] - f_tier["hit_rate"], 4
                    )

        return summary
```

---

## Task 4: DuckDB Ablation Schema Verification

**File**: `scripts/init_ablation_db.py`

```python
"""
Initialize the ablation_results DuckDB table.
Should already exist from Week 7 — this script is a safety net.
"""

import duckdb


def init_ablation_schema(db_path: str = "ablation.db") -> None:
    conn = duckdb.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ablation_results (
            run_id           VARCHAR,
            file_id          VARCHAR,
            query_id         VARCHAR,
            index_type       VARCHAR,
            hit_at_5         BOOLEAN,
            reciprocal_rank  DOUBLE,
            query_latency_ms DOUBLE,
            complexity_tier  VARCHAR,
            depth_level      INTEGER,
            created_at       TIMESTAMP,
            PRIMARY KEY (run_id, file_id, query_id, index_type)
        )
    """)
    print(f"ablation_results table ready in {db_path}")
    conn.close()


if __name__ == "__main__":
    init_ablation_schema()
```

---

## Task 5: Analysis Script — Stratified Results

**File**: `scripts/analyze_ablation.py`

```python
"""
Analyze ablation results and produce defense-ready tables + plots.

Usage:
    python scripts/analyze_ablation.py --db ablation.db [--run_id latest]

Outputs:
    - Console: stratified hit-rate table
    - docs/ablation_results.md: formatted Markdown with tables
    - docs/ablation_plots/: PNG plots
"""

import argparse
from pathlib import Path

import duckdb
import structlog

log = structlog.get_logger(__name__)


def analyze(db_path: str, run_id: str | None = None) -> dict:
    """
    Analyze ablation results.
    
    Returns summary dict with tables and narrative.
    """
    conn = duckdb.connect(db_path, read_only=True)

    # Get latest run_id if not specified
    if run_id is None or run_id == "latest":
        result = conn.execute(
            "SELECT run_id FROM ablation_results ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if not result:
            raise ValueError("No ablation results found")
        run_id = result[0]

    print(f"Analyzing run: {run_id}")

    # ---- Overall metrics ----
    overall = conn.execute("""
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
    """, [run_id]).fetchall()

    print("\n=== Overall Results ===")
    print(f"{'Index':<10} {'Queries':>8} {'Hit@5':>8} {'MRR':>8} {'Latency':>10}")
    print("-" * 50)
    for row in overall:
        print(f"{row[0]:<10} {row[1]:>8} {row[2]:>8.4f} {row[3]:>8.4f} {row[4]:>10.2f}ms")

    # ---- Stratified by complexity ----
    stratified = conn.execute("""
        SELECT
            complexity_tier,
            index_type,
            COUNT(*) as n,
            AVG(CAST(hit_at_5 AS DOUBLE)) as hit_rate,
            AVG(reciprocal_rank) as mrr
        FROM ablation_results
        WHERE run_id = ?
        GROUP BY complexity_tier, index_type
        ORDER BY complexity_tier, index_type
    """, [run_id]).fetchall()

    print("\n=== Stratified by Complexity ===")
    print(f"{'Tier':<12} {'Index':<10} {'N':>5} {'Hit@5':>8} {'MRR':>8}")
    print("-" * 50)
    for row in stratified:
        print(f"{row[0]:<12} {row[1]:<10} {row[2]:>5} {row[3]:>8.4f} {row[4]:>8.4f}")

    # ---- Compute advantage ----
    advantage = conn.execute("""
        WITH raptor AS (
            SELECT complexity_tier,
                   AVG(CAST(hit_at_5 AS DOUBLE)) as hit_rate
            FROM ablation_results
            WHERE run_id = ? AND index_type = 'raptor'
            GROUP BY complexity_tier
        ),
        flat AS (
            SELECT complexity_tier,
                   AVG(CAST(hit_at_5 AS DOUBLE)) as hit_rate
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
    """, [run_id, run_id]).fetchall()

    print("\n=== RAPTOR Advantage ===")
    print(f"{'Tier':<12} {'RAPTOR':>8} {'Flat':>8} {'Δ':>8} {'≥10%?':>6}")
    print("-" * 45)
    for row in advantage:
        delta_pct = row[3] * 100
        check = "✓" if row[3] >= 0.10 else "✗"
        print(f"{row[0]:<12} {row[1]:>8.4f} {row[2]:>8.4f} {delta_pct:>+7.1f}% {check:>6}")

    conn.close()

    return {
        "run_id": run_id,
        "overall": overall,
        "stratified": stratified,
        "advantage": advantage,
    }


def generate_markdown_report(results: dict, output_path: str = "docs/ablation_results.md") -> None:
    """Generate a defense-ready Markdown report from analysis results."""
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
        "| Tier | RAPTOR | Flat | Advantage | Target ≥10% |",
        "|------|-------:|-----:|----------:|:-----------:|",
    ]

    for row in results["advantage"]:
        delta_pct = row[3] * 100
        check = "✓" if row[3] >= 0.10 else "✗"
        lines.append(f"| {row[0]} | {row[1]:.4f} | {row[2]:.4f} | {delta_pct:+.1f}% | {check} |")

    lines += [
        "",
        "## Interpretation",
        "",
        "*(Fill in after running the study)*",
        "",
        "### If RAPTOR advantage ≥ 10% on MODERATE/HIGH:",
        "The hierarchical clustering adds meaningful semantic context for complex SAS blocks. "
        "The LLM-generated cluster summaries capture cross-block relationships (macro calls, "
        "dataset dependencies) that individual partition embeddings miss.",
        "",
        "### If RAPTOR advantage < 10%:",
        "With only ~330 KB pairs, the RAPTOR tree is shallow (typically 2–3 levels). "
        "The clustering benefit likely requires ≥1,000 pairs to form meaningfully distinct "
        "semantic clusters. This is an honest negative result — document it and propose the "
        "1,000+ pair threshold as future work.",
        "",
        "---",
        "",
        f"> *Ablation run: `{results['run_id']}`*",
    ]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written to {output_path}")


def generate_plots(db_path: str, run_id: str, output_dir: str = "docs/ablation_plots") -> None:
    """
    Generate defense-ready plots:
      1. Bar chart: hit-rate@5 by complexity tier (RAPTOR vs Flat)
      2. Box plot: reciprocal rank distribution
      3. Latency comparison scatter
    """
    import matplotlib.pyplot as plt
    import numpy as np

    conn = duckdb.connect(db_path, read_only=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # ---- Plot 1: Hit-rate bar chart ----
    tiers = ["LOW", "MODERATE", "HIGH"]
    raptor_hrs = []
    flat_hrs = []

    for tier in tiers:
        for idx_type, target_list in [("raptor", raptor_hrs), ("flat", flat_hrs)]:
            result = conn.execute("""
                SELECT AVG(CAST(hit_at_5 AS DOUBLE))
                FROM ablation_results
                WHERE run_id = ? AND index_type = ? AND complexity_tier = ?
            """, [run_id, idx_type, tier]).fetchone()
            target_list.append(result[0] if result[0] else 0)

    x = np.arange(len(tiers))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    bars1 = ax.bar(x - width/2, raptor_hrs, width, label="RAPTOR", color="#2196F3")
    bars2 = ax.bar(x + width/2, flat_hrs, width, label="Flat", color="#FF9800")

    ax.set_ylabel("Hit-rate@5")
    ax.set_xlabel("Complexity Tier")
    ax.set_title("RAPTOR vs Flat: Hit-rate@5 by Complexity")
    ax.set_xticks(x)
    ax.set_xticklabels(tiers)
    ax.legend()
    ax.set_ylim(0, 1.0)
    ax.axhline(y=0.82, color="r", linestyle="--", alpha=0.5, label="Target (0.82)")
    ax.legend()

    # Add value labels
    for bar in bars1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f"{bar.get_height():.3f}", ha="center", va="bottom", fontsize=9)
    for bar in bars2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f"{bar.get_height():.3f}", ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    plt.savefig(Path(output_dir) / "hit_rate_by_complexity.png", dpi=150)
    plt.close()

    # ---- Plot 2: MRR box plot ----
    fig, ax = plt.subplots(figsize=(8, 5))

    raptor_mrrs = conn.execute("""
        SELECT reciprocal_rank FROM ablation_results
        WHERE run_id = ? AND index_type = 'raptor'
    """, [run_id]).fetchall()

    flat_mrrs = conn.execute("""
        SELECT reciprocal_rank FROM ablation_results
        WHERE run_id = ? AND index_type = 'flat'
    """, [run_id]).fetchall()

    data = [[r[0] for r in raptor_mrrs], [r[0] for r in flat_mrrs]]
    bp = ax.boxplot(data, labels=["RAPTOR", "Flat"], patch_artist=True)
    bp["boxes"][0].set_facecolor("#2196F3")
    bp["boxes"][1].set_facecolor("#FF9800")

    ax.set_ylabel("Reciprocal Rank")
    ax.set_title("MRR Distribution: RAPTOR vs Flat")
    plt.tight_layout()
    plt.savefig(Path(output_dir) / "mrr_distribution.png", dpi=150)
    plt.close()

    # ---- Plot 3: Latency scatter ----
    fig, ax = plt.subplots(figsize=(8, 5))

    raptor_lat = conn.execute("""
        SELECT query_latency_ms FROM ablation_results
        WHERE run_id = ? AND index_type = 'raptor'
    """, [run_id]).fetchall()

    flat_lat = conn.execute("""
        SELECT query_latency_ms FROM ablation_results
        WHERE run_id = ? AND index_type = 'flat'
    """, [run_id]).fetchall()

    ax.hist([r[0] for r in raptor_lat], bins=30, alpha=0.6, label="RAPTOR", color="#2196F3")
    ax.hist([r[0] for r in flat_lat], bins=30, alpha=0.6, label="Flat", color="#FF9800")
    ax.set_xlabel("Query Latency (ms)")
    ax.set_ylabel("Frequency")
    ax.set_title("Query Latency Distribution")
    ax.legend()
    plt.tight_layout()
    plt.savefig(Path(output_dir) / "latency_distribution.png", dpi=150)
    plt.close()

    conn.close()
    log.info("ablation_plots_saved", output_dir=output_dir)


def main():
    parser = argparse.ArgumentParser(description="Analyze ablation results")
    parser.add_argument("--db", default="ablation.db")
    parser.add_argument("--run_id", default="latest")
    parser.add_argument("--plots", action="store_true", help="Generate plots (requires matplotlib)")
    args = parser.parse_args()

    results = analyze(args.db, args.run_id if args.run_id != "latest" else None)
    generate_markdown_report(results)

    if args.plots:
        generate_plots(args.db, results["run_id"])


if __name__ == "__main__":
    main()
```

---

## Task 6: Regression Guard Test

**File**: `tests/regression/test_ablation.py`

```python
"""
Regression guard: RAPTOR retrieval quality.

Runs in CI (<60s). Fails if:
  - RAPTOR hit-rate@5 < 0.82 (overall)
  - RAPTOR advantage < 0.10 on MODERATE/HIGH tiers

These thresholds are from cahier §11.
"""

import duckdb
import pytest
from pathlib import Path

ABLATION_DB = "ablation.db"


@pytest.fixture
def conn():
    if not Path(ABLATION_DB).exists():
        pytest.skip("ablation.db not found — run ablation study first")
    return duckdb.connect(ABLATION_DB, read_only=True)


def test_raptor_hit_rate_overall(conn):
    """RAPTOR hit-rate@5 must be > 0.82."""
    result = conn.execute("""
        SELECT AVG(CAST(hit_at_5 AS DOUBLE))
        FROM ablation_results
        WHERE index_type = 'raptor'
    """).fetchone()
    assert result[0] is not None, "No RAPTOR results found"
    assert result[0] > 0.82, f"RAPTOR hit-rate@5 = {result[0]:.4f}, expected > 0.82"


def test_raptor_advantage_moderate_high(conn):
    """RAPTOR advantage must be ≥ 10% on MODERATE/HIGH combined."""
    raptor = conn.execute("""
        SELECT AVG(CAST(hit_at_5 AS DOUBLE))
        FROM ablation_results
        WHERE index_type = 'raptor' AND complexity_tier IN ('MODERATE', 'HIGH')
    """).fetchone()

    flat = conn.execute("""
        SELECT AVG(CAST(hit_at_5 AS DOUBLE))
        FROM ablation_results
        WHERE index_type = 'flat' AND complexity_tier IN ('MODERATE', 'HIGH')
    """).fetchone()

    assert raptor[0] is not None and flat[0] is not None
    advantage = raptor[0] - flat[0]
    assert advantage >= 0.10, (
        f"RAPTOR advantage on MOD/HIGH = {advantage:.4f}, expected ≥ 0.10. "
        f"RAPTOR={raptor[0]:.4f}, Flat={flat[0]:.4f}"
    )


def test_ablation_query_count(conn):
    """Must have at least 500 query pairs (50 files × 10 queries × 2 indexes)."""
    result = conn.execute(
        "SELECT COUNT(*) FROM ablation_results"
    ).fetchone()
    assert result[0] >= 1000, f"Expected ≥ 1000 rows (500 queries × 2 indexes), got {result[0]}"
```

---

## Task 7: Run the Study — Step-by-Step Commands

```bash
# 1. Initialize the ablation DB (if not already done in Week 7)
python scripts/init_ablation_db.py

# 2. Build the flat index from existing RAPTOR nodes
python -c "
from partition.evaluation.flat_index import build_flat_index
build_flat_index('lancedb_data')
"

# 3. Generate 500 queries
python -c "
import json
from partition.evaluation.query_generator import generate_queries
# Load partitions from SQLite
import sqlite3
conn = sqlite3.connect('partition_store.db')
rows = conn.execute('SELECT partition_id, source_file_id, partition_type, complexity_score FROM partition_ir').fetchall()
partitions = [
    {'partition_id': r[0], 'source_file_id': r[1], 'partition_type': r[2],
     'complexity_tier': 'HIGH' if r[3] > 0.7 else ('MODERATE' if r[3] > 0.3 else 'LOW')}
    for r in rows
]
queries = generate_queries(partitions, n_per_file=10)
with open('ablation_queries.json', 'w') as f:
    json.dump(queries, f, indent=2)
print(f'Generated {len(queries)} queries')
"

# 4. Run the ablation study
python -c "
import json
from partition.evaluation.ablation_runner import AblationRunner
from partition.embedding.nomic_embed import embed_text  # from Week 5-6

with open('ablation_queries.json') as f:
    queries = json.load(f)

runner = AblationRunner(
    lancedb_path='lancedb_data',
    duckdb_path='ablation.db',
    embed_fn=embed_text,
)
summary = runner.run(queries)
print(json.dumps(summary, indent=2))
"

# 5. Analyze results + generate report
python scripts/analyze_ablation.py --db ablation.db --plots

# 6. Run regression guards
pytest tests/regression/test_ablation.py -v

# 7. Verify total query count
python -c "
import duckdb
conn = duckdb.connect('ablation.db', read_only=True)
n = conn.execute('SELECT COUNT(*) FROM ablation_results').fetchone()[0]
print(f'Total ablation rows: {n} (expect ≥ 1000)')
"
```

---

## File Structure After Week 12

```
partition/
├── evaluation/
│   ├── __init__.py
│   ├── flat_index.py               ← Task 1
│   ├── query_generator.py          ← Task 2
│   └── ablation_runner.py          ← Task 3
scripts/
├── init_ablation_db.py             ← Task 4
├── analyze_ablation.py             ← Task 5
tests/
├── regression/
│   ├── test_ablation.py            ← Task 6
│   ├── test_ece.py                 (from Week 4)
│   └── test_boundary_accuracy.py   (from Week 3-4)
docs/
├── ablation_results.md             ← generated by Task 5
├── ablation_plots/
│   ├── hit_rate_by_complexity.png   ← generated
│   ├── mrr_distribution.png        ← generated
│   └── latency_distribution.png    ← generated
ablation.db                         ← DuckDB with ablation_results table
ablation_queries.json               ← 500 generated queries
```

---

## Dependencies (pip)

```
matplotlib>=3.8     # for ablation plots
# Already installed: duckdb, lancedb, numpy, structlog
```

---

## ✅ Week 12 Success Checklist

| # | Check | Target | Command |
|---|-------|--------|---------|
| 1 | Flat index built | Level-0 nodes only | `python -c "import lancedb; ..."` |
| 2 | 500 queries generated | `ablation_queries.json` ≥ 500 entries | `python -c "import json; ..."` |
| 3 | Ablation run complete | ≥ 1000 rows in `ablation_results` | `SELECT COUNT(*) FROM ablation_results` |
| 4 | RAPTOR hit@5 > 0.82 | Overall hit-rate | `pytest tests/regression/test_ablation.py::test_raptor_hit_rate_overall` |
| 5 | RAPTOR advantage ≥ 10% | On MODERATE/HIGH | `pytest tests/regression/test_ablation.py::test_raptor_advantage_moderate_high` |
| 6 | Results doc generated | `docs/ablation_results.md` exists | `cat docs/ablation_results.md` |
| 7 | Plots generated | 3 PNG files in `docs/ablation_plots/` | `ls docs/ablation_plots/*.png` |
| 8 | Defense narrative written | Interpretation section filled | Manual review |

---

## Evaluation Metrics — Week 12

| Metric | Target | How to Measure |
|--------|--------|----------------|
| RAPTOR hit-rate@5 (overall) | > 0.82 | `SELECT AVG(hit_at_5) WHERE index_type='raptor'` |
| RAPTOR advantage (MOD/HIGH) | ≥ 10% | Stratified DuckDB query |
| MRR (RAPTOR) | > 0.60 | `SELECT AVG(reciprocal_rank)` |
| Query count | ≥ 500 | `SELECT COUNT(DISTINCT query_id)` |
| Latency overhead | < 50ms | `AVG(raptor_latency) - AVG(flat_latency)` |
| Statistical significance | p < 0.05 | McNemar's test on hit@5 (optional) |

---

## Common Pitfalls

1. **Flat index includes cluster nodes** — The flat index must contain ONLY `level==0` nodes. If you include cluster summaries, the comparison is unfair (flat would have more noise, not less info).
2. **Query embedding drift** — Use the exact same `embed_fn` (Nomic Embed v1.5) for both RAPTOR and flat queries. Different models / quantization → invalid comparison.
3. **Small corpus bias** — 50 files × 10 queries = 500. If most files are LOW complexity, the MODERATE/HIGH stratification will have low sample count. Use stratified query generation (Task 2).
4. **Null ablation result** — If RAPTOR shows no advantage, don't fabricate results. Document honestly: "KB too small for clustering benefit; propose 1,000+ pair threshold." This is still a valid finding.
5. **DuckDB `ablation_results` primary key** — Composite PK `(run_id, file_id, query_id, index_type)`. If you re-run, use a new `run_id` or delete old data.
6. **Matplotlib backend** — On headless servers, set `matplotlib.use("Agg")` before importing pyplot.

---

## If RAPTOR Shows No Advantage — Defense Strategy

From the cahier Risk Register:

> **Risk**: RAPTOR ablation shows null result  
> **Probability**: LOW  
> **Impact**: MEDIUM  
> **Mitigation**: Document honestly — "KB too small for clustering benefit; propose 1,000+ pair threshold." Still a publishable negative result.

Defense narrative:
- "We adapted RAPTOR for SAS code partitioning and tested it rigorously."
- "At 330 KB pairs, the GMM clustering produces 2–3 levels with limited semantic diversity."
- "The methodology is sound and extensible — with a larger KB (1,000+ pairs), we hypothesize the advantage would materialize."
- "The ablation study itself is a contribution: it establishes baseline expectations for hierarchical code retrieval."

---

> *Week 12 — Ablation Study: RAPTOR vs Flat Retrieval*
