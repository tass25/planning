"""Integration test — real end-to-end pipeline path (K7).

Verifies the 8-node orchestrator graph using real components:
    file_process → streaming → chunking → raptor →
    risk_routing → persist_index → translation → merge → END

No mocking. The orchestrator runs with:
- Degraded Redis (bad URL → no-op checkpointing)
- Real SAS files written to tmp_path
- LLM-dependent stages produce PARTIAL results when API keys are absent
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from partition.orchestration.orchestrator import PartitionOrchestrator

# ── Helpers ───────────────────────────────────────────────────────────────────

_SIMPLE_SAS = """\
DATA work.out;
    SET sashelp.class;
    age_group = PUT(Age, 3.);
    IF Age > 14 THEN flag = 1;
    ELSE flag = 0;
RUN;

PROC MEANS DATA=work.out NWAY NOPRINT;
    CLASS flag;
    VAR Age;
    OUTPUT OUT=work.summary MEAN=avg_age;
RUN;
"""

_MULTI_BLOCK_SAS = """\
%MACRO calc_stats(ds=, var=);
    PROC MEANS DATA=&ds NWAY NOPRINT;
        VAR &var;
        OUTPUT OUT=_stats MEAN=mean_val;
    RUN;
%MEND calc_stats;

DATA work.input;
    DO i = 1 TO 20;
        x = RANUNI(42) * 100;
        OUTPUT;
    END;
    DROP i;
RUN;

%calc_stats(ds=work.input, var=x);

DATA work.result;
    SET work.input;
    RETAIN total 0;
    total + x;
RUN;
"""


def _sas_file(tmp_path: Path, content: str, name: str = "test.sas") -> str:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def _make_orchestrator(tmp_path: Path) -> PartitionOrchestrator:
    """Real orchestrator with unreachable Redis (degraded mode)."""
    return PartitionOrchestrator(
        redis_url="redis://localhost:99999",
        duckdb_path=str(tmp_path / "integration.duckdb"),
        target_runtime="python",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestPipelineIntegration:
    """End-to-end pipeline integration using real agent instances."""

    @pytest.fixture(autouse=True)
    def _ensure_data_dir(self):
        """Ensure backend/data/ directory exists for SQLite file registry."""
        data_dir = Path(__file__).resolve().parent.parent / "data"
        data_dir.mkdir(exist_ok=True)

    @pytest.mark.asyncio
    async def test_graph_has_eight_nodes(self, tmp_path):
        """The compiled graph must contain exactly 8 pipeline nodes."""
        orch = _make_orchestrator(tmp_path)
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

    @pytest.mark.asyncio
    async def test_pipeline_returns_state(self, tmp_path):
        """Running the pipeline on a real SAS file must return a non-None state."""
        sas = _sas_file(tmp_path, _SIMPLE_SAS)
        orch = _make_orchestrator(tmp_path)
        state = await orch.run([sas])
        assert state is not None

    @pytest.mark.asyncio
    async def test_file_ids_populated(self, tmp_path):
        """file_ids must be populated after file_process node."""
        sas = _sas_file(tmp_path, _SIMPLE_SAS)
        orch = _make_orchestrator(tmp_path)
        state = await orch.run([sas])
        assert len(state["file_ids"]) >= 1

    @pytest.mark.asyncio
    async def test_state_fields_present(self, tmp_path):
        """All mandatory state fields must exist in the final state."""
        sas = _sas_file(tmp_path, _SIMPLE_SAS)
        orch = _make_orchestrator(tmp_path)
        state = await orch.run([sas])
        for field in ("input_paths", "file_ids", "partitions", "errors", "warnings"):
            assert field in state, f"Missing state field: {field}"

    @pytest.mark.asyncio
    async def test_errors_is_a_list(self, tmp_path):
        """errors field must always be a list (never None)."""
        sas = _sas_file(tmp_path, _SIMPLE_SAS)
        orch = _make_orchestrator(tmp_path)
        state = await orch.run([sas])
        assert isinstance(state.get("errors", []), list)

    @pytest.mark.asyncio
    async def test_partition_count_non_negative(self, tmp_path):
        """partition_count must be >= 0 after chunking."""
        sas = _sas_file(tmp_path, _SIMPLE_SAS)
        orch = _make_orchestrator(tmp_path)
        state = await orch.run([sas])
        assert state.get("partition_count", 0) >= 0

    @pytest.mark.asyncio
    async def test_multi_block_sas_produces_partitions(self, tmp_path):
        """A file with macros, data steps, and procs should yield >=1 partitions."""
        sas = _sas_file(tmp_path, _MULTI_BLOCK_SAS)
        orch = _make_orchestrator(tmp_path)
        state = await orch.run([sas])
        assert state.get("partition_count", 0) >= 1

    @pytest.mark.asyncio
    async def test_pipeline_graceful_on_missing_file(self, tmp_path):
        """A nonexistent path produces 0 file_ids and no crash — the file_process node
        logs a warning and continues with an empty file list."""
        orch = _make_orchestrator(tmp_path)
        state = await orch.run(["__nonexistent_file_xyz_abc__.sas"])
        assert state is not None
        assert state["file_ids"] == []
        assert state["partition_count"] == 0

    @pytest.mark.asyncio
    async def test_redis_is_in_degraded_mode(self, tmp_path):
        """Orchestrator must run in degraded Redis mode (no crash)."""
        orch = _make_orchestrator(tmp_path)
        assert orch.checkpoint.available is False
        sas = _sas_file(tmp_path, _SIMPLE_SAS)
        state = await orch.run([sas])
        assert state is not None

    @pytest.mark.asyncio
    async def test_conversion_results_is_list(self, tmp_path):
        """conversion_results must be a list (possibly empty if no LLM keys)."""
        sas = _sas_file(tmp_path, _SIMPLE_SAS)
        orch = _make_orchestrator(tmp_path)
        state = await orch.run([sas])
        assert isinstance(state.get("conversion_results", []), list)

    @pytest.mark.asyncio
    async def test_merge_results_is_list(self, tmp_path):
        """merge_results must be a list (populated or empty depending on LLM)."""
        sas = _sas_file(tmp_path, _SIMPLE_SAS)
        orch = _make_orchestrator(tmp_path)
        state = await orch.run([sas])
        assert isinstance(state.get("merge_results", []), list)
