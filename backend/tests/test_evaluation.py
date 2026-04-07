"""Tests for Week 12 — Evaluation / Ablation Study modules."""

import tempfile

import duckdb
import lancedb
import numpy as np
import pyarrow as pa
import pytest

# ── Query Generator ───────────────────────────────────────────────────

from partition.evaluation.query_generator import QUERY_TEMPLATES, generate_queries


class TestQueryGenerator:
    def test_generates_queries(self):
        partitions = [
            {"source_file_id": "f-001", "partition_type": "DATA_STEP_BASIC", "complexity_tier": "LOW"},
            {"source_file_id": "f-001", "partition_type": "PROC_SQL", "complexity_tier": "MODERATE"},
            {"source_file_id": "f-001", "partition_type": "PROC_MEANS", "complexity_tier": "HIGH"},
        ]
        queries = generate_queries(partitions, n_per_file=3)
        assert len(queries) == 3
        for q in queries:
            assert "query_id" in q
            assert "query_text" in q
            assert "expected_partition_type" in q

    def test_reproducibility_with_seed(self):
        partitions = [
            {"source_file_id": "f-001", "partition_type": "DATA_STEP_BASIC", "complexity_tier": "LOW"},
        ] * 5
        q1 = generate_queries(partitions, n_per_file=5, seed=42)
        q2 = generate_queries(partitions, n_per_file=5, seed=42)
        assert [q["query_text"] for q in q1] == [q["query_text"] for q in q2]

    def test_multiple_files(self):
        partitions = [
            {"source_file_id": "f-001", "partition_type": "DATA_STEP_BASIC", "complexity_tier": "LOW"},
            {"source_file_id": "f-002", "partition_type": "PROC_FREQ", "complexity_tier": "HIGH"},
        ]
        queries = generate_queries(partitions, n_per_file=1)
        file_ids = {q["file_id"] for q in queries}
        assert len(file_ids) == 2

    def test_template_coverage(self):
        assert len(QUERY_TEMPLATES) >= 10
        for ptype, templates in QUERY_TEMPLATES.items():
            assert len(templates) >= 1


# ── Flat Index Builder ────────────────────────────────────────────────

from partition.evaluation.flat_index import build_flat_index


class TestFlatIndexBuilder:
    def test_build_flat_from_raptor(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = lancedb.connect(tmpdir)

            # Create mock RAPTOR nodes
            schema = pa.schema([
                pa.field("node_id", pa.string()),
                pa.field("level", pa.int32()),
                pa.field("summary", pa.string()),
                pa.field("summary_tier", pa.string()),
                pa.field("embedding", pa.list_(pa.float32(), 768)),
                pa.field("child_ids", pa.string()),
                pa.field("file_id", pa.string()),
                pa.field("partition_ids", pa.string()),
                pa.field("created_at", pa.string()),
            ])

            records = []
            for i in range(5):
                records.append({
                    "node_id": f"n-{i}",
                    "level": 0 if i < 3 else 1,
                    "summary": f"Summary {i}",
                    "summary_tier": "DATA_STEP_BASIC",
                    "embedding": np.random.randn(768).astype(np.float32).tolist(),
                    "child_ids": "[]",
                    "file_id": "f-001",
                    "partition_ids": "[]",
                    "created_at": "2024-01-01T00:00:00Z",
                })

            db.create_table("raptor_nodes", data=records, schema=schema)

            result = build_flat_index(tmpdir)
            assert result["flat_node_count"] == 3  # Only level-0
            assert result["raptor_node_count"] == 5

            flat = db.open_table("flat_nodes")
            assert len(flat.to_pandas()) == 3


# ── Ablation Runner ──────────────────────────────────────────────────

from partition.evaluation.ablation_runner import AblationRunner


class TestAblationRunner:
    def test_runner_computes_summary(self, tmp_path):
        tmpdir = str(tmp_path / "lance")
        db = lancedb.connect(tmpdir)

        embed_dim = 768
        records = []
        for i in range(10):
            records.append({
                "node_id": f"n-{i}",
                "summary": f"DATA step {i}",
                "embedding": np.random.randn(embed_dim).astype(np.float32).tolist(),
                "summary_tier": "DATA_STEP_BASIC" if i % 2 == 0 else "PROC_SQL",
                "file_id": "f-001",
                "partition_ids": "[]",
                "created_at": "2024-01-01",
            })

        schema_raptor = pa.schema([
            pa.field("node_id", pa.string()),
            pa.field("level", pa.int32()),
            pa.field("summary", pa.string()),
            pa.field("summary_tier", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), 768)),
            pa.field("child_ids", pa.string()),
            pa.field("file_id", pa.string()),
            pa.field("partition_ids", pa.string()),
            pa.field("created_at", pa.string()),
        ])

        raptor_records = [{**r, "level": 0, "child_ids": "[]"} for r in records]
        db.create_table("raptor_nodes", data=raptor_records, schema=schema_raptor)

        flat_schema = pa.schema([
            pa.field("node_id", pa.string()),
            pa.field("summary", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), 768)),
            pa.field("partition_type", pa.string()),
            pa.field("file_id", pa.string()),
            pa.field("partition_ids", pa.string()),
            pa.field("created_at", pa.string()),
        ])
        flat_records = [{
            "node_id": r["node_id"],
            "summary": r["summary"],
            "embedding": r["embedding"],
            "partition_type": r["summary_tier"],
            "file_id": r["file_id"],
            "partition_ids": r["partition_ids"],
            "created_at": r["created_at"],
        } for r in records]
        db.create_table("flat_nodes", data=flat_records, schema=flat_schema)

        duckdb_path = str(tmp_path / "test_ablation.duckdb")

        runner = AblationRunner(
            lancedb_path=tmpdir,
            duckdb_path=duckdb_path,
            embed_fn=lambda text: np.random.randn(embed_dim).tolist(),
            k=3,
        )

        queries = [
            {
                "query_id": "q-1",
                "file_id": "f-001",
                "query_text": "Convert DATA step to Python",
                "expected_partition_type": "DATA_STEP_BASIC",
                "complexity_tier": "LOW",
            },
            {
                "query_id": "q-2",
                "file_id": "f-001",
                "query_text": "Convert PROC SQL to pandas",
                "expected_partition_type": "PROC_SQL",
                "complexity_tier": "MODERATE",
            },
        ]

        summary = runner.run(queries)
        runner.duckdb_conn.close()

        assert "raptor" in summary
        assert "flat" in summary
        assert summary["raptor"]["n_queries"] == 2
        assert "hit_rate_at_5" in summary["raptor"]
        assert "mrr" in summary["raptor"]
        assert "advantage" in summary


# ── Init Script (schema) ─────────────────────────────────────────────

from scripts.ablation.init_ablation_db import init_ablation_schema


class TestInitAblationDB:
    def test_creates_table(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        init_ablation_schema(db_path)

        conn = duckdb.connect(db_path, read_only=True)
        tables = conn.execute("SHOW TABLES").fetchall()
        conn.close()
        table_names = [t[0] for t in tables]
        assert "ablation_results" in table_names
