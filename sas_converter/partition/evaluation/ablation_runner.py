"""AblationRunner — Execute RAPTOR vs Flat retrieval comparison.

For each query:
  1. Embed the query text
  2. Search RAPTOR index -> top-5 results
  3. Search Flat index -> top-5 results
  4. Compare against ground truth
  5. Record metrics to DuckDB ablation_results
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import uuid4

import duckdb
import lancedb
import structlog

log = structlog.get_logger(__name__)


class AblationRunner:
    """Runs the RAPTOR vs Flat ablation study."""

    def __init__(
        self,
        lancedb_path: str,
        duckdb_path: str,
        embed_fn,
        raptor_table: str = "raptor_nodes",
        flat_table: str = "flat_nodes",
        k: int = 5,
    ):
        self.db = lancedb.connect(lancedb_path)
        self.duckdb_conn = duckdb.connect(duckdb_path)
        self.embed_fn = embed_fn
        self.raptor_table = raptor_table
        self.flat_table = flat_table
        self.k = k
        self.run_id = str(uuid4())

        # Ensure table exists
        self.duckdb_conn.execute("""
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
                created_at       VARCHAR
            )
        """)

    def run(self, queries: list[dict]) -> dict:
        """Execute the full ablation study. Returns summary dict."""
        log.info("ablation_started", run_id=self.run_id, n_queries=len(queries))

        results: dict[str, list[dict]] = {"raptor": [], "flat": []}

        for i, query in enumerate(queries):
            query_text = query["query_text"]
            expected_type = query["expected_partition_type"]
            complexity = query["complexity_tier"]

            embedding = self.embed_fn(query_text)

            raptor_result = self._search_and_evaluate(
                table_name=self.raptor_table,
                index_type="raptor",
                embedding=embedding,
                expected_type=expected_type,
                query=query,
                complexity=complexity,
            )
            results["raptor"].append(raptor_result)

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
        table = self.db.open_table(table_name)

        start = time.perf_counter()
        hits = table.search(embedding).limit(self.k).to_pandas()
        latency_ms = (time.perf_counter() - start) * 1000

        # Check partition_type or summary_tier column
        type_col = "partition_type" if "partition_type" in hits.columns else "summary_tier"
        hit_types = hits[type_col].tolist() if type_col in hits.columns else []
        hit_at_k = expected_type in hit_types

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
            "depth_level": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._write_result(result)
        return result

    def _write_result(self, result: dict) -> None:
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
        summary: dict = {}

        for idx_type in ("raptor", "flat"):
            items = results[idx_type]
            n = len(items)
            if n == 0:
                continue

            hit_rate = sum(1 for r in items if r["hit_at_5"]) / n
            mrr = sum(r["reciprocal_rank"] for r in items) / n
            avg_latency = sum(r["query_latency_ms"] for r in items) / n

            by_tier: dict[str, dict] = {}
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

        if "raptor" in summary and "flat" in summary:
            summary["advantage"] = {
                "hit_rate_delta": round(
                    summary["raptor"]["hit_rate_at_5"] - summary["flat"]["hit_rate_at_5"], 4
                ),
                "mrr_delta": round(
                    summary["raptor"]["mrr"] - summary["flat"]["mrr"], 4
                ),
            }
            for tier in ("LOW", "MODERATE", "HIGH"):
                r_tier = summary["raptor"]["by_complexity"].get(tier, {})
                f_tier = summary["flat"]["by_complexity"].get(tier, {})
                if r_tier and f_tier:
                    summary["advantage"][f"{tier}_hit_rate_delta"] = round(
                        r_tier["hit_rate"] - f_tier["hit_rate"], 4
                    )

        return summary
