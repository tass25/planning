"""Knowledge Base retrieval for translation context.

Queries LanceDB with filtering by partition_type, failure_mode,
and target_runtime.
"""

from __future__ import annotations

import re
from typing import Optional

import lancedb
import structlog

logger = structlog.get_logger()

# Only allow safe identifier characters in WHERE clause values.
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_. -]+$")

# Module-level singleton: one LanceDB connection per db_path.
_db_connections: dict[str, lancedb.DBConnection] = {}


def _get_db(db_path: str) -> lancedb.DBConnection:
    """Return a shared LanceDB connection (singleton per path)."""
    if db_path not in _db_connections:
        _db_connections[db_path] = lancedb.connect(db_path)
    return _db_connections[db_path]


class KBQueryClient:
    """Query the sas_python_examples KB in LanceDB."""

    TABLE_NAME = "sas_python_examples"
    MIN_RELEVANCE = 0.50

    def __init__(self, db_path: str = "data/lancedb"):
        self.db = _get_db(db_path)

    def retrieve_examples(
        self,
        query_embedding: list[float],
        partition_type: str,
        failure_mode: Optional[str] = None,
        target_runtime: str = "python",
        k: int = 5,
    ) -> list[dict]:
        """Retrieve k most relevant KB examples for a partition.

        Filters:
          - partition_type must match (exact)
          - failure_mode must match (if specified)
          - target_runtime must match
          - verified = True only
          - cosine similarity >= MIN_RELEVANCE
        """
        if self.TABLE_NAME not in self.db.table_names():
            logger.warning("kb_table_missing", table=self.TABLE_NAME)
            return []

        table = self.db.open_table(self.TABLE_NAME)

        def _safe(val: str) -> str:
            """Validate value is safe for WHERE clause embedding."""
            if not _SAFE_VALUE.match(val):
                raise ValueError(f"Unsafe filter value: {val!r}")
            return val

        where_parts = [
            f"partition_type = '{_safe(partition_type)}'",
            f"target_runtime = '{_safe(target_runtime)}'",
            "verified = true",
        ]
        if failure_mode:
            where_parts.append(f"failure_mode = '{_safe(failure_mode)}'")
        where_clause = " AND ".join(where_parts)

        try:
            results = (
                table.search(query_embedding)
                .where(where_clause)
                .limit(k)
                .to_pandas()
            )

            if "_distance" in results.columns:
                results["similarity"] = 1 - results["_distance"]
                results = results[results["similarity"] >= self.MIN_RELEVANCE]

            examples = []
            for _, row in results.iterrows():
                issues_raw = row.get("issues_text", "") or ""
                # Convert pipe-separated string back to list for template rendering
                issues_list = [i.strip() for i in issues_raw.split("|") if i.strip()]
                examples.append({
                    "example_id":  row["example_id"],
                    "sas_code":    row["sas_code"],
                    "python_code": row["python_code"],
                    "similarity":  row.get("similarity", 0),
                    "failure_mode": row.get("failure_mode", ""),
                    "category":    row.get("category", ""),
                    "issues":      issues_list,
                })

            logger.info(
                "kb_retrieved",
                partition_type=partition_type,
                failure_mode=failure_mode,
                k=k,
                returned=len(examples),
            )
            return examples

        except Exception as e:
            logger.warning("kb_query_failed", error=str(e))
            return []
