"""KB LanceDB Writer — manages the ``sas_python_examples`` table.

Provides insert, count, and coverage-stats operations for the
Knowledge Base stored in LanceDB with 768-dim Nomic embeddings
and IVF index (64 partitions, cosine metric).

Schema (16 fields) follows cahier des charges §5.3.

Azure migration note (Week 9):
    Embeddings produced by NomicEmbedder; LLM generation chain
    uses Azure OpenAI (primary) + Groq (fallback verifier).
"""

from __future__ import annotations

import uuid
from typing import Optional

import lancedb
import pyarrow as pa
import structlog

logger = structlog.get_logger()

# ── KB PyArrow schema ─────────────────────────────────────────────────────────

KB_SCHEMA = pa.schema(
    [
        pa.field("example_id", pa.string()),
        pa.field("sas_code", pa.string()),
        pa.field("python_code", pa.string()),
        pa.field("embedding", pa.list_(pa.float32(), 768)),
        pa.field("partition_type", pa.string()),
        pa.field("complexity_tier", pa.string()),
        pa.field("target_runtime", pa.string()),
        pa.field("verified", pa.bool_()),
        pa.field("source", pa.string()),
        pa.field("failure_mode", pa.string()),
        pa.field("verification_method", pa.string()),
        pa.field("verification_score", pa.float32()),
        pa.field("category", pa.string()),
        pa.field("version", pa.int32()),
        pa.field("superseded_by", pa.string()),
        pa.field("created_at", pa.string()),
        # pipe-separated list of pattern-specific pitfalls (from teammate KB issues field)
        pa.field("issues_text", pa.string()),
    ]
)


class KBWriter:
    """Manage the Knowledge Base in LanceDB.

    The table ``sas_python_examples`` stores verified SAS→Python
    pairs with 768-dim Nomic embeddings.  An IVF index is (re)built
    automatically when the table reaches ``NUM_PARTITIONS * 2`` rows.

    Usage::

        writer = KBWriter()
        writer.insert_pairs(pairs)
        writer.count()           # -> int
        writer.coverage_stats()  # -> {"DATA_STEP_BASIC": 30, ...}
    """

    TABLE_NAME = "sas_python_examples"
    NUM_PARTITIONS = 64

    def __init__(
        self,
        db_path: str = "",
        duckdb_path: str = "",
    ) -> None:
        from config.constants import DUCKDB_PATH as _DD
        from config.constants import LANCEDB_PATH as _LD

        self.db = lancedb.connect(db_path or _LD)
        self.duckdb_path = duckdb_path or _DD

    # ── Insert ────────────────────────────────────────────────────────────

    def insert_pairs(self, pairs: list[dict]) -> int:
        """Insert verified pairs into LanceDB.

        Creates the table on first call; appends on subsequent calls.
        Rebuilds the IVF index when enough rows exist.

        Args:
            pairs: List of dicts matching ``KB_SCHEMA`` fields.

        Returns:
            Number of inserted pairs.
        """
        if not pairs:
            return 0

        # Ensure every pair has a version (default 1 for new inserts)
        for pair in pairs:
            pair.setdefault("version", 1)
            pair.setdefault("superseded_by", "")

        if self.TABLE_NAME in self.db.table_names():
            table = self.db.open_table(self.TABLE_NAME)
            table.add(pairs)
        else:
            table = self.db.create_table(self.TABLE_NAME, data=pairs, schema=KB_SCHEMA)

        self._log_changelog(pairs, action="insert")

        # Rebuild IVF index when there are enough rows
        try:
            if len(table) >= self.NUM_PARTITIONS * 2:
                table.create_index(
                    metric="cosine",
                    num_partitions=self.NUM_PARTITIONS,
                    num_sub_vectors=16,
                    replace=True,
                )
                logger.info(
                    "kb_index_rebuilt",
                    rows=len(table),
                    partitions=self.NUM_PARTITIONS,
                )
        except Exception as exc:
            logger.debug("kb_index_skip", reason=str(exc))

        logger.info("kb_pairs_inserted", count=len(pairs), total=len(table))
        return len(pairs)

    # ── Count ─────────────────────────────────────────────────────────────

    def count(self) -> int:
        """Return total number of KB examples."""
        if self.TABLE_NAME not in self.db.table_names():
            return 0
        return len(self.db.open_table(self.TABLE_NAME))

    # ── Coverage stats ────────────────────────────────────────────────────

    def coverage_stats(self) -> dict[str, int]:
        """Report pairs per category.

        Returns:
            Dict mapping category name → count,
            e.g. ``{"DATA_STEP_BASIC": 30, "PROC_SQL": 28, ...}``
        """
        if self.TABLE_NAME not in self.db.table_names():
            return {}
        table = self.db.open_table(self.TABLE_NAME)
        df = table.to_pandas()
        return df.groupby("category").size().to_dict()

    # ── Search (for downstream retrieval) ─────────────────────────────────

    def _log_changelog(self, pairs: list[dict], action: str = "insert") -> None:
        """Write changelog entries to DuckDB for traceability."""
        try:
            from partition.orchestration.audit import _get_duckdb

            con = _get_duckdb(self.duckdb_path)
            for pair in pairs:
                version = pair.get("version", 1)
                con.execute(
                    "INSERT INTO kb_changelog VALUES (?, ?, ?, ?, ?, ?, ?, NOW())",
                    [
                        str(uuid.uuid4()),
                        pair.get("example_id", ""),
                        action,
                        None,
                        version,
                        pair.get("source", "unknown"),
                        f"{action} {pair.get('category', 'unknown')} pair v{version}",
                    ],
                )
        except Exception as exc:
            logger.debug("kb_changelog_write_skipped", error=str(exc))

    def search(
        self,
        embedding: list[float],
        top_k: int = 5,
        category_filter: Optional[str] = None,
    ) -> list[dict]:
        """Search KB by embedding similarity.

        Args:
            embedding: 768-dim query embedding.
            top_k: Number of results.
            category_filter: Optional category filter.

        Returns:
            List of matching KB records as dicts.
        """
        if self.TABLE_NAME not in self.db.table_names():
            return []

        table = self.db.open_table(self.TABLE_NAME)
        query = table.search(embedding).limit(top_k)

        if category_filter:
            query = query.where(f"category = '{category_filter}'")

        return query.to_list()
