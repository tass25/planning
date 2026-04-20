"""Tests for Week 11 — Merge Layer (L4) + Continuous Learning."""

import ast
import tempfile

import duckdb

# ── Import Consolidator ──────────────────────────────────────────────
from partition.merge.import_consolidator import consolidate_imports


class TestImportConsolidator:
    def test_dedup_and_ordering(self):
        imports = [
            ["os", "pandas", "numpy"],
            ["pandas", "datetime", "scipy"],
        ]
        result = consolidate_imports(imports)
        lines = result.split("\n")
        # stdlib first
        assert lines[0].startswith("import datetime") or lines[0].startswith("import os")
        # pandas appears exactly once
        assert result.count("import pandas as pd") == 1

    def test_canonical_aliases(self):
        imports = [["statsmodels.api"]]
        result = consolidate_imports(imports)
        assert "import statsmodels.api as sm" in result

    def test_empty_imports(self):
        result = consolidate_imports([])
        assert result == ""

    def test_numpy_alias(self):
        imports = [["numpy"]]
        result = consolidate_imports(imports)
        assert "import numpy as np" in result

    def test_matplotlib_alias(self):
        imports = [["matplotlib.pyplot"]]
        result = consolidate_imports(imports)
        assert "import matplotlib.pyplot as plt" in result


# ── Dependency Injector ───────────────────────────────────────────────

from partition.merge.dependency_injector import (
    NameRegistry,
    add_cross_file_stubs,
    build_name_registry,
    sas_name_to_snake,
)


class TestDependencyInjector:
    def test_sas_name_to_snake(self):
        assert sas_name_to_snake("WORK.TEMP_CUSTOMERS") == "work_temp_customers"
        assert sas_name_to_snake("SASDATA.SALES") == "sasdata_sales"
        assert sas_name_to_snake("mytable") == "mytable"

    def test_registry_roundtrip(self):
        reg = NameRegistry()
        py = reg.register("WORK.TEMP", "file-001")
        assert py == "work_temp"
        assert reg.lookup("WORK.TEMP") == "work_temp"
        assert reg.get_producer("work_temp") == "file-001"

    def test_build_from_partitions(self):
        partitions = [
            {"raw_code": "DATA WORK.OUT; SET WORK.IN; RUN;"},
            {"raw_code": "PROC MEANS DATA=SASDATA.SALES; RUN;"},
        ]
        reg = build_name_registry(partitions, "file-001")
        assert reg.lookup("WORK.OUT") == "work_out"

    def test_cross_file_stubs(self):
        code = "df = work_temp"
        result = add_cross_file_stubs(code, ["WORK.EXT"], {"WORK.EXT": "other.sas"})
        assert "# NOTE: 'WORK.EXT' expected from external file 'other.sas'" in result

    def test_no_stubs_when_empty(self):
        code = "x = 1"
        result = add_cross_file_stubs(code, [], {})
        assert result == "x = 1"


# ── Script Merger ─────────────────────────────────────────────────────

from partition.merge.script_merger import merge_script


class TestScriptMerger:
    def test_basic_merge(self):
        crs = [
            {"python_code": "x = 1", "imports_detected": ["os"], "status": "SUCCESS"},
            {"python_code": "y = x + 1", "imports_detected": ["pandas"], "status": "SUCCESS"},
        ]
        parts = [
            {"raw_code": "x=1;", "line_start": 1, "line_end": 1, "partition_type": "DATA_STEP"},
            {"raw_code": "y=x+1;", "line_start": 2, "line_end": 2, "partition_type": "DATA_STEP"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            result = merge_script(crs, parts, "f-001", "test.sas", output_dir=tmpdir)
            assert result["syntax_valid"] is True
            assert result["status"] == "SUCCESS"
            assert result["block_count"] == 2
            ast.parse(result["python_script"])

    def test_human_review_inserts_todo(self):
        crs = [
            {"python_code": "", "imports_detected": [], "status": "HUMAN_REVIEW"},
        ]
        parts = [
            {
                "raw_code": "DATA complex; RUN;",
                "line_start": 1,
                "line_end": 3,
                "partition_type": "DATA_STEP",
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            result = merge_script(crs, parts, "f-002", "complex.sas", output_dir=tmpdir)
            assert "TODO: HUMAN_REVIEW" in result["python_script"]
            assert result["human_review_count"] == 1

    def test_ordering_by_line_start(self):
        crs = [
            {"python_code": "b = 2", "imports_detected": [], "status": "SUCCESS"},
            {"python_code": "a = 1", "imports_detected": [], "status": "SUCCESS"},
        ]
        parts = [
            {"raw_code": "b=2;", "line_start": 10, "line_end": 10},
            {"raw_code": "a=1;", "line_start": 1, "line_end": 1},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            result = merge_script(crs, parts, "f-003", "order.sas", output_dir=tmpdir)
            script = result["python_script"]
            assert script.index("a = 1") < script.index("b = 2")

    def test_partial_status(self):
        crs = [
            {
                "python_code": "# PARTIAL: failed\nx = 1",
                "imports_detected": [],
                "status": "PARTIAL",
            },
        ]
        parts = [
            {"raw_code": "x=1;", "line_start": 1, "line_end": 1},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            result = merge_script(crs, parts, "f-004", "partial.sas", output_dir=tmpdir)
            assert result["partial_count"] == 1
            assert result["status"] == "HAS_GAPS"


# ── Report Agent ──────────────────────────────────────────────────────

from partition.merge.report_agent import ReportAgent


class TestReportAgent:
    def test_generate_report(self):
        agent = ReportAgent()
        crs = [
            {"status": "SUCCESS", "failure_mode_flagged": ""},
            {"status": "PARTIAL", "failure_mode_flagged": "RETAIN"},
        ]
        merged = {
            "block_count": 2,
            "partial_count": 1,
            "human_review_count": 0,
            "syntax_valid": True,
            "output_path": "output/test_converted.py",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            report = agent.generate_report(
                source_file_id="f-005",
                source_path="test.sas",
                merged_script=merged,
                conversion_results=crs,
                output_dir=tmpdir,
            )
            assert report["total_blocks"] == 2
            assert report["success_count"] == 1
            from pathlib import Path

            assert Path(report["report_md_path"]).exists()
            assert Path(report["report_html_path"]).exists()


# ── Feedback Ingestion ────────────────────────────────────────────────


class TestFeedbackIngestion:
    def test_ingest_accepted(self):
        from partition.retraining.feedback_ingestion import FeedbackIngestionAgent

        added_items = []

        class FakeTable:
            def add(self, items):
                added_items.extend(items)

        conn = duckdb.connect(":memory:")

        agent = FeedbackIngestionAgent(
            lancedb_table=FakeTable(),
            embed_fn=lambda text: [0.1] * 768,
            cross_verifier_fn=lambda sas, py: {"confidence": 0.90},
            duckdb_conn=conn,
            confidence_threshold=0.85,
        )

        result = agent.ingest(
            conversion_id="c-001",
            partition_id="p-001",
            sas_code="DATA out; SET in; RUN;",
            corrected_python="df_out = df_in.copy()",
        )

        assert result["accepted"] is True
        assert len(added_items) == 1
        assert added_items[0]["example_id"] == result["new_kb_example_id"]

    def test_ingest_rejected(self):
        from partition.retraining.feedback_ingestion import FeedbackIngestionAgent

        conn = duckdb.connect(":memory:")

        agent = FeedbackIngestionAgent(
            lancedb_table=None,
            embed_fn=lambda text: [0.0] * 768,
            cross_verifier_fn=lambda sas, py: {"confidence": 0.50},
            duckdb_conn=conn,
            confidence_threshold=0.85,
        )

        result = agent.ingest(
            conversion_id="c-002",
            partition_id="p-002",
            sas_code="DATA x; RUN;",
            corrected_python="x = 1",
        )

        assert result["accepted"] is False
        assert "confidence" in result["rejection_reason"]


# ── Quality Monitor ───────────────────────────────────────────────────


class TestQualityMonitor:
    def test_evaluate_triggers_alert(self):
        from partition.retraining.quality_monitor import ConversionQualityMonitor

        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE conversion_results (
                status VARCHAR, llm_confidence DOUBLE,
                failure_mode_flagged VARCHAR
            )
        """)
        # Insert 10 rows: 3 SUCCESS, 7 PARTIAL
        for i in range(3):
            conn.execute(
                "INSERT INTO conversion_results VALUES (?, ?, ?)",
                ["SUCCESS", 0.9, ""],
            )
        for i in range(7):
            conn.execute(
                "INSERT INTO conversion_results VALUES (?, ?, ?)",
                ["PARTIAL", 0.5, "RETAIN"],
            )

        monitor = ConversionQualityMonitor(conn, success_target=0.70)
        result = monitor.evaluate()

        assert result["success_rate"] == 0.3
        assert len(result["alerts"]) > 0

    def test_no_alert_when_healthy(self):
        from partition.retraining.quality_monitor import ConversionQualityMonitor

        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE conversion_results (
                status VARCHAR, llm_confidence DOUBLE,
                failure_mode_flagged VARCHAR
            )
        """)
        for i in range(10):
            conn.execute(
                "INSERT INTO conversion_results VALUES (?, ?, ?)",
                ["SUCCESS", 0.95, ""],
            )

        monitor = ConversionQualityMonitor(conn)
        result = monitor.evaluate()

        assert result["success_rate"] == 1.0
        assert len(result["alerts"]) == 0


# ── Retrain Trigger ───────────────────────────────────────────────────


class TestRetrainTrigger:
    def test_no_trigger_when_clean(self):
        from partition.retraining.retrain_trigger import RetrainTrigger

        conn = duckdb.connect(":memory:")
        trigger = RetrainTrigger(conn)
        decision = trigger.evaluate()
        assert decision.should_retrain is False

    def test_consecutive_low_success(self):
        from partition.retraining.retrain_trigger import RetrainTrigger

        conn = duckdb.connect(":memory:")
        conn.execute("""
            CREATE TABLE quality_metrics (
                success_rate DOUBLE, created_at VARCHAR
            )
        """)
        conn.execute("INSERT INTO quality_metrics VALUES (0.50, '2024-01-01')")
        conn.execute("INSERT INTO quality_metrics VALUES (0.60, '2024-01-02')")

        trigger = RetrainTrigger(conn, consecutive_failures=2)
        decision = trigger.evaluate()
        assert decision.should_retrain is True
        assert "consecutive" in decision.trigger_reason
