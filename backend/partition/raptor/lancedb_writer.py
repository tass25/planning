"""RAPTORLanceDBWriter — persist RAPTOR nodes to LanceDB with cosine IVF index."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import lancedb
import pyarrow as pa
import structlog

from partition.models.partition_ir import RAPTORNode

logger = structlog.get_logger()

# Arrow schema for the raptor_nodes table
RAPTOR_SCHEMA = pa.schema(
    [
        pa.field("node_id", pa.string()),
        pa.field("level", pa.int32()),
        pa.field("summary", pa.string()),
        pa.field("summary_tier", pa.string()),
        pa.field("embedding", pa.list_(pa.float32(), 768)),
        pa.field("child_ids", pa.string()),  # JSON array
        pa.field("cluster_label", pa.int32()),
        pa.field("file_id", pa.string()),
        pa.field("partition_ids", pa.string()),  # JSON array
        pa.field("created_at", pa.string()),
    ]
)


class RAPTORLanceDBWriter:
    """Write / query RAPTOR nodes in LanceDB.

    - Creates a ``raptor_nodes`` table on first write.
    - Appends on subsequent writes.
    - Builds a cosine IVF index when the table has ≥ 64 vectors
      (``NUM_PARTITIONS * 2``).
    """

    TABLE_NAME = "raptor_nodes"
    NUM_PARTITIONS = 32  # IVF index parameter

    def __init__(self, db_path: str = "data/lancedb"):
        self.db = lancedb.connect(db_path)
        logger.info("lancedb_connected", db_path=db_path)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert_nodes(self, nodes: list[RAPTORNode]) -> int:
        """Persist a batch of RAPTORNode objects.

        Returns the number of rows written.
        """
        records = []
        for node in nodes:
            records.append(
                {
                    "node_id": str(node.node_id),
                    "level": node.level,
                    "summary": node.summary,
                    "summary_tier": node.summary_tier,
                    "embedding": node.embedding,
                    "child_ids": json.dumps([str(c) for c in node.child_ids]),
                    "cluster_label": (node.cluster_label if node.cluster_label is not None else -1),
                    "file_id": str(node.file_id),
                    "partition_ids": json.dumps(node.partition_ids),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        if self.TABLE_NAME in self.db.table_names():
            table = self.db.open_table(self.TABLE_NAME)
            table.add(records)
        else:
            table = self.db.create_table(
                self.TABLE_NAME,
                data=records,
                schema=RAPTOR_SCHEMA,
            )

        # Build / rebuild IVF index when enough data
        try:
            if len(table) >= self.NUM_PARTITIONS * 2:
                table.create_index(
                    metric="cosine",
                    num_partitions=self.NUM_PARTITIONS,
                    num_sub_vectors=16,
                    replace=True,
                )
                logger.info("lancedb_index_created", table_len=len(table))
        except Exception:
            pass  # Index creation fails on small tables — that's OK

        return len(records)

    # ------------------------------------------------------------------
    # Read / query
    # ------------------------------------------------------------------

    def query_similar(
        self,
        query_embedding: list[float],
        k: int = 5,
        level: Optional[int] = None,
        file_id: Optional[str] = None,
    ) -> list[dict]:
        """Cosine-similarity search over RAPTOR nodes.

        Used by the TranslationAgent (L3) for context retrieval.
        """
        if self.TABLE_NAME not in self.db.table_names():
            return []

        table = self.db.open_table(self.TABLE_NAME)
        query = table.search(query_embedding).limit(k)

        if level is not None:
            query = query.where(f"level = {level}")
        if file_id:
            query = query.where(f"file_id = '{file_id}'")

        return query.to_list()

    def count_nodes(self, file_id: Optional[str] = None) -> int:
        """Return the total number of RAPTOR nodes (optionally per file)."""
        if self.TABLE_NAME not in self.db.table_names():
            return 0
        table = self.db.open_table(self.TABLE_NAME)
        if file_id:
            return len(table.search().where(f"file_id = '{file_id}'").to_list())
        return len(table)
