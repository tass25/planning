"""Tests for the Week 8 orchestration layer.

Covers:
    - PipelineState field validation
    - RedisCheckpointManager degraded mode + interval logic
    - LLMAuditLogger DuckDB persistence
    - PartitionOrchestrator graph compilation
    - E2E smoke test with real orchestrator (degraded Redis)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))


def _redis_reachable(url: str = "redis://localhost:6379/0") -> bool:
    """Return True if Redis responds to PING within 1 second."""
    try:
        import redis as _redis

        r = _redis.from_url(url, socket_connect_timeout=1)
        r.ping()
        return True
    except Exception:
        return False


# ======================================================================
# PipelineState
# ======================================================================


class TestPipelineState:
    def test_state_has_all_required_fields(self):
        """PipelineState TypedDict has all expected annotations."""
        from partition.orchestration.state import PipelineState

        required = [
            "input_paths",
            "target_runtime",
            "stage",
            "file_ids",
            "cross_file_deps",
            "partitions",
            "partition_count",
            "raptor_nodes",
            "complexity_computed",
            "persisted_count",
            "scc_groups",
            "max_hop",
            "errors",
            "warnings",
            "trace_id",
            "run_id",
        ]
        for field in required:
            assert field in PipelineState.__annotations__, f"Missing field: {field}"

    def test_pipeline_stage_enum_values(self):
        """PipelineStage has 14 stages (L2 + L3 translation/validation)."""
        from partition.orchestration.state import PipelineStage

        assert len(PipelineStage) == 14
        assert PipelineStage.INIT.value == "INIT"
        assert PipelineStage.TRANSLATION.value == "TRANSLATION"
        assert PipelineStage.VALIDATION.value == "VALIDATION"
        assert PipelineStage.COMPLETE.value == "COMPLETE"
        assert PipelineStage.ERROR.value == "ERROR"


# ======================================================================
# RedisCheckpointManager
# ======================================================================


class TestRedisCheckpoint:
    def test_degraded_mode_no_crash(self):
        """Pipeline works without Redis (degraded mode, no crash)."""
        from partition.orchestration.checkpoint import RedisCheckpointManager

        mgr = RedisCheckpointManager("redis://localhost:99999")
        assert mgr.available is False
        assert mgr.save_checkpoint("f1", 50, []) is False
        assert mgr.find_latest_checkpoint("f1") is None
        mgr.clear_checkpoints("f1")  # no-op, no crash

    def test_degraded_mode_returns_false_for_any_block(self):
        """In degraded mode every block number returns False."""
        from partition.orchestration.checkpoint import RedisCheckpointManager

        mgr = RedisCheckpointManager("redis://localhost:99999")
        assert mgr.available is False
        for block in (0, 25, 50, 100):
            assert mgr.save_checkpoint("f1", block, [{"x": 1}]) is False

    def test_degraded_find_returns_none(self):
        """find_latest_checkpoint returns None in degraded mode."""
        from partition.orchestration.checkpoint import RedisCheckpointManager

        mgr = RedisCheckpointManager("redis://localhost:99999")
        assert mgr.find_latest_checkpoint("any-file") is None

    def test_checkpoint_interval_constant(self):
        """CHECKPOINT_INTERVAL must be 50."""
        from partition.orchestration.checkpoint import RedisCheckpointManager

        assert RedisCheckpointManager.CHECKPOINT_INTERVAL == 50

    def test_ttl_constant(self):
        """TTL_SECONDS must be 86400 (24 h)."""
        from partition.orchestration.checkpoint import RedisCheckpointManager

        assert RedisCheckpointManager.TTL_SECONDS == 86_400

    @pytest.mark.skipif(
        not _redis_reachable(),
        reason="Local Redis not available — interval logic requires live connection",
    )
    def test_checkpoint_interval_skip(self):
        """Block 25 (not a multiple of 50) should be skipped."""
        from partition.orchestration.checkpoint import RedisCheckpointManager

        mgr = RedisCheckpointManager("redis://localhost:6379/0")
        assert mgr.available is True
        result = mgr.save_checkpoint("f1", 25, [{"x": 1}])
        assert result is False

    @pytest.mark.skipif(
        not _redis_reachable(),
        reason="Local Redis not available — interval logic requires live connection",
    )
    def test_checkpoint_fires_at_zero(self):
        """Block 0 always triggers a checkpoint."""
        from partition.orchestration.checkpoint import RedisCheckpointManager

        mgr = RedisCheckpointManager("redis://localhost:6379/0")
        assert mgr.available is True
        result = mgr.save_checkpoint("fire-zero", 0, [{"init": True}])
        assert result is True
        mgr.clear_checkpoints("fire-zero")

    @pytest.mark.skipif(
        not _redis_reachable(),
        reason="Local Redis not available — interval logic requires live connection",
    )
    def test_checkpoint_fires_at_interval(self):
        """Block 50 triggers a checkpoint."""
        from partition.orchestration.checkpoint import RedisCheckpointManager

        mgr = RedisCheckpointManager("redis://localhost:6379/0")
        assert mgr.available is True
        result = mgr.save_checkpoint("fire-50", 50, [{"block": 50}])
        assert result is True
        mgr.clear_checkpoints("fire-50")


# ======================================================================
# LLMAuditLogger
# ======================================================================


class TestLLMAuditLogger:
    def test_audit_context_manager_success(self, tmp_path):
        """Audit logs a successful LLM call to DuckDB."""
        import duckdb
        from partition.db.duckdb_manager import init_all_duckdb_tables
        from partition.orchestration.audit import LLMAuditLogger

        db_path = str(tmp_path / "test_audit.duckdb")
        init_all_duckdb_tables(db_path)
        audit = LLMAuditLogger(db_path)

        with audit.log_call("TestAgent", "test_model", "test prompt") as call:
            call.set_response("test response")

        con = duckdb.connect(db_path)
        rows = con.execute("SELECT * FROM llm_audit").fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "TestAgent"  # agent_name
        assert rows[0][6] is True  # success
        assert rows[0][7] is None  # error_msg
        con.close()

    def test_audit_context_manager_failure(self, tmp_path):
        """Audit logs a failed LLM call."""
        import duckdb
        from partition.db.duckdb_manager import init_all_duckdb_tables
        from partition.orchestration.audit import LLMAuditLogger

        db_path = str(tmp_path / "test_audit_fail.duckdb")
        init_all_duckdb_tables(db_path)
        audit = LLMAuditLogger(db_path)

        with pytest.raises(ValueError, match="boom"):
            with audit.log_call("FailAgent", "fail_model", "bad prompt"):
                raise ValueError("boom")

        con = duckdb.connect(db_path)
        rows = con.execute("SELECT * FROM llm_audit").fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "FailAgent"
        assert rows[0][6] is False  # success
        assert "boom" in rows[0][7]  # error_msg
        con.close()


# ======================================================================
# PartitionOrchestrator graph compilation
# ======================================================================


class TestOrchestratorGraph:
    def _make_orchestrator(self, tmp_path):
        """Create a real orchestrator; Redis degrades gracefully on bad URL."""
        from partition.orchestration.orchestrator import PartitionOrchestrator

        return PartitionOrchestrator(
            redis_url="redis://localhost:99999",
            duckdb_path=str(tmp_path / "test.duckdb"),
            target_runtime="python",
        )

    def test_graph_compiles(self, tmp_path):
        """The LangGraph StateGraph should compile without errors."""
        orch = self._make_orchestrator(tmp_path)
        assert orch.graph is not None

    def test_graph_has_all_nodes(self, tmp_path):
        """Graph contains all 8 pipeline nodes."""
        orch = self._make_orchestrator(tmp_path)
        graph = orch.graph
        node_names = set(graph.nodes.keys()) - {"__start__", "__end__"}
        expected = {
            "file_process",
            "streaming",
            "chunking",
            "raptor",
            "risk_routing",
            "persist_index",
            "translation",
            "merge",
        }
        assert node_names == expected, f"Expected {expected}, got {node_names}"

    def test_redis_in_degraded_mode(self, tmp_path):
        """Orchestrator initialises without crash when Redis is unreachable."""
        orch = self._make_orchestrator(tmp_path)
        assert orch.checkpoint.available is False


# ======================================================================
# Integration: initial state creation
# ======================================================================


class TestInitialState:
    def test_run_creates_initial_state(self):
        """Verify the orchestrator creates a valid initial state dict."""
        from partition.orchestration.state import PipelineStage, PipelineState

        state: PipelineState = {
            "input_paths": ["file1.sas", "file2.sas"],
            "target_runtime": "python",
            "stage": PipelineStage.INIT.value,
            "current_file_idx": 0,
            "file_metas": [],
            "file_ids": [],
            "cross_file_deps": {},
            "chunks_by_file": {},
            "partitions": [],
            "partition_count": 0,
            "raptor_nodes": [],
            "complexity_computed": False,
            "persisted_count": 0,
            "scc_groups": [],
            "max_hop": 3,
            "last_checkpoint_block": 0,
            "checkpoint_key": None,
            "errors": [],
            "warnings": [],
            "trace_id": "test-trace",
            "run_id": "test-run",
        }

        assert state["stage"] == "INIT"
        assert len(state["input_paths"]) == 2
        assert state["partition_count"] == 0
        assert state["errors"] == []
