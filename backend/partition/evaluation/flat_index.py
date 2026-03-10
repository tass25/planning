"""FlatIndexBuilder — Extract level-0 nodes from RAPTOR for ablation baseline.

The flat index contains only leaf-level embeddings (level == 0) from the
RAPTOR tree, stripped of hierarchical cluster context. This serves as the
baseline for the RAPTOR vs Flat ablation study.
"""

from __future__ import annotations

from datetime import datetime, timezone

import lancedb
import pyarrow as pa
import structlog

log = structlog.get_logger(__name__)

FLAT_SCHEMA = pa.schema(
    [
        pa.field("node_id", pa.string()),
        pa.field("summary", pa.string()),
        pa.field("embedding", pa.list_(pa.float32(), 768)),
        pa.field("partition_type", pa.string()),
        pa.field("file_id", pa.string()),
        pa.field("partition_ids", pa.string()),
        pa.field("created_at", pa.string()),
    ]
)


def build_flat_index(
    lancedb_path: str,
    raptor_table: str = "raptor_nodes",
    flat_table: str = "flat_nodes",
) -> dict:
    """Extract level-0 nodes from RAPTOR index into a flat LanceDB table.

    Returns summary dict with node count.
    """
    db = lancedb.connect(lancedb_path)
    source = db.open_table(raptor_table)
    df = source.to_pandas()

    # Filter to level-0 (leaf) nodes only
    leaves = df[df["level"] == 0].copy()

    if leaves.empty:
        log.warning("no_level0_nodes_found", raptor_table=raptor_table)
        return {"flat_node_count": 0}

    # Build flat records
    records = []
    for _, row in leaves.iterrows():
        records.append(
            {
                "node_id": row["node_id"],
                "summary": row.get("summary", ""),
                "embedding": row["embedding"],
                "partition_type": row.get("summary_tier", ""),
                "file_id": row.get("file_id", ""),
                "partition_ids": row.get("partition_ids", "[]"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    # Create / overwrite flat table
    if flat_table in db.table_names():
        db.drop_table(flat_table)
    db.create_table(flat_table, data=records, schema=FLAT_SCHEMA)

    log.info(
        "flat_index_built",
        raptor_nodes=len(df),
        flat_nodes=len(records),
        table=flat_table,
    )
    return {"flat_node_count": len(records), "raptor_node_count": len(df)}
