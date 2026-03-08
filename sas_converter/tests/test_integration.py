"""Integration test — full pipeline path (K7).

Verifies the 8-node orchestrator graph end-to-end with mocked agents:
    file_process → streaming → chunking → raptor →
    risk_routing → persist_index → translation → merge → END

This catches regressions like missing merge wiring (A3) and engine=None (A1)
automatically.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from partition.models.enums import (
    ConversionStatus,
    PartitionType,
    RiskLevel,
)
from partition.models.file_metadata import FileMetadata
from partition.models.partition_ir import PartitionIR
from partition.models.conversion_result import ConversionResult


# ── Fixtures ──────────────────────────────────────────────────────────

FILE_ID = uuid4()
BLOCK_ID = uuid4()


def _make_file_meta(path: str = "test.sas") -> FileMetadata:
    return FileMetadata(
        file_id=FILE_ID,
        file_path=path,
        encoding="utf-8",
        content_hash="abc123",
        file_size_bytes=200,
        line_count=10,
        lark_valid=True,
    )


def _make_partition() -> PartitionIR:
    return PartitionIR(
        block_id=BLOCK_ID,
        file_id=FILE_ID,
        partition_type=PartitionType.DATA_STEP,
        source_code="data test; x=1; run;",
        line_start=1,
        line_end=3,
        risk_level=RiskLevel.LOW,
    )


def _make_conversion() -> ConversionResult:
    return ConversionResult(
        block_id=BLOCK_ID,
        file_id=FILE_ID,
        python_code="x = 1",
        status=ConversionStatus.SUCCESS,
        llm_confidence=0.95,
        validation_passed=True,
    )


# ── Integration test ─────────────────────────────────────────────────


class TestPipelineIntegration:
    """End-to-end pipeline integration with mocked agent internals."""

    @pytest.fixture(autouse=True)
    def _setup_orchestrator(self, tmp_path):
        """Create an orchestrator with fully mocked infrastructure."""
        self.tmp = tmp_path

        # Patch infrastructure that requires external services
        with (
            patch("partition.orchestration.checkpoint.RedisCheckpointManager") as mock_redis,
            patch("partition.orchestration.audit.LLMAuditLogger") as mock_audit,
        ):
            mock_redis_inst = MagicMock()
            mock_redis_inst.available = False
            mock_redis_inst.find_latest_checkpoint.return_value = None
            mock_redis_inst.save_checkpoint.return_value = False
            mock_redis_inst.clear_checkpoints.return_value = None
            mock_redis.return_value = mock_redis_inst

            mock_audit_inst = MagicMock()
            mock_audit.return_value = mock_audit_inst

            from partition.orchestration.orchestrator import PartitionOrchestrator

            self.orch = PartitionOrchestrator(
                redis_url="redis://localhost:99999",
                duckdb_path=str(tmp_path / "test.duckdb"),
                target_runtime="python",
            )

    @pytest.mark.asyncio
    async def test_full_pipeline_path(self, tmp_path):
        """Run the full 8-node pipeline and verify merge output is populated."""
        fm = _make_file_meta("test.sas")
        partition = _make_partition()
        conversion = _make_conversion()

        # Mock each agent's process() to return realistic data
        mock_file_processor = AsyncMock()
        mock_file_processor.process.return_value = ([fm], {})

        mock_streaming = AsyncMock()
        mock_streaming.return_value = {str(FILE_ID): [{"block": "data test; x=1; run;"}]}

        mock_chunking = AsyncMock()
        mock_chunking.process.return_value = [partition]

        mock_raptor = AsyncMock()
        mock_raptor.process.return_value = []

        mock_risk_router = AsyncMock()
        mock_risk_router.process.return_value = [partition]

        mock_persistence = AsyncMock()
        mock_persistence.process.return_value = 1

        mock_index = AsyncMock()
        mock_index.process.return_value = {"sccs": [], "hop_cap": 3}

        mock_translation = AsyncMock()
        mock_translation.translate_partition.return_value = conversion

        mock_merge = AsyncMock()
        mock_merge.process.return_value = {
            "merged_script": {
                "script_id": str(uuid4()),
                "python_script": "x = 1",
                "status": "SUCCESS",
                "output_path": str(tmp_path / "output.py"),
                "block_count": 1,
            },
            "report": {"file_id": str(FILE_ID), "status": "SUCCESS"},
        }

        with (
            patch(
                "partition.entry.file_processor.FileProcessor",
                return_value=mock_file_processor,
            ),
            patch(
                "partition.streaming.pipeline.run_streaming_pipeline",
                side_effect=mock_streaming,
            ),
            patch(
                "partition.chunking.chunking_agent.ChunkingAgent",
                return_value=mock_chunking,
            ),
            patch(
                "partition.raptor.raptor_agent.RAPTORPartitionAgent",
                return_value=mock_raptor,
            ),
            patch(
                "partition.complexity.risk_router.RiskRouter",
                return_value=mock_risk_router,
            ),
            patch(
                "partition.persistence.persistence_agent.PersistenceAgent",
                return_value=mock_persistence,
            ),
            patch(
                "partition.index.index_agent.IndexAgent",
                return_value=mock_index,
            ),
            patch(
                "partition.translation.translation_pipeline.TranslationPipeline",
                return_value=mock_translation,
            ),
            patch(
                "partition.merge.merge_agent.MergeAgent",
                return_value=mock_merge,
            ),
        ):
            # Clear agent cache so mocks are used
            self.orch._agents.clear()

            final_state = await self.orch.run(["test.sas"])

        # ── Assertions ────────────────────────────────────────────
        # Pipeline completed (didn't crash)
        assert final_state is not None

        # File processing happened
        assert len(final_state["file_metas"]) == 1
        assert final_state["file_ids"] == [str(FILE_ID)]

        # Translation produced results
        assert len(final_state["conversion_results"]) == 1
        assert final_state["validation_passed"] == 1

        # Merge stage was reached and produced results
        assert len(final_state["merge_results"]) == 1
        assert final_state["merge_results"][0]["merged_script"]["status"] == "SUCCESS"

        # No fatal errors
        assert len(final_state.get("errors", [])) == 0

    @pytest.mark.asyncio
    async def test_pipeline_fatal_on_file_process_failure(self, tmp_path):
        """L2-A failure should be fatal (RuntimeError), not swallowed."""
        with patch(
            "partition.entry.file_processor.FileProcessor",
        ) as mock_fp_cls:
            mock_fp = AsyncMock()
            mock_fp.process.side_effect = RuntimeError("disk error")
            mock_fp_cls.return_value = mock_fp

            self.orch._agents.clear()

            with pytest.raises(RuntimeError, match="L2-A file processing failed"):
                await self.orch.run(["nonexistent.sas"])

    @pytest.mark.asyncio
    async def test_graph_has_eight_nodes(self):
        """The compiled graph should contain exactly 8 pipeline nodes."""
        graph = self.orch.graph
        # LangGraph compiled graph has a .nodes dict
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
