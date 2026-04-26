"""Tests for StrategyAgent (L2-D).

Run with:
    cd sas_converter
    ../venv/Scripts/python -m pytest tests/test_strategy_agent.py -v
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from partition.complexity.strategy_agent import StrategyAgent
from partition.models.enums import PartitionType, RiskLevel
from partition.models.partition_ir import PartitionIR


def _run(coro):
    return asyncio.run(coro)


def _make_partition(
    ptype: PartitionType,
    risk: RiskLevel,
    confidence: float = 0.80,
) -> PartitionIR:
    return PartitionIR(
        file_id=uuid4(),
        partition_type=ptype,
        source_code="",
        line_start=1,
        line_end=10,
        metadata={
            "nesting_depth": 0,
            "is_ambiguous": False,
            "complexity_confidence": confidence,
        },
        risk_level=risk,
    )


# ── Strategy routing ──────────────────────────────────────────────────────────


class TestStrategyRouting:
    def test_high_risk_gets_structural_grouping(self):
        p = _make_partition(PartitionType.DATA_STEP, RiskLevel.HIGH)
        agent = StrategyAgent()
        result = _run(agent.process([p]))
        assert result[0].metadata["strategy"] == "STRUCTURAL_GROUPING"

    def test_uncertain_gets_human_review(self):
        p = _make_partition(PartitionType.DATA_STEP, RiskLevel.UNCERTAIN)
        agent = StrategyAgent()
        result = _run(agent.process([p]))
        assert result[0].metadata["strategy"] == "HUMAN_REVIEW"

    def test_low_data_step_gets_flat_partition(self):
        p = _make_partition(PartitionType.DATA_STEP, RiskLevel.LOW)
        agent = StrategyAgent()
        result = _run(agent.process([p]))
        assert result[0].metadata["strategy"] == "FLAT_PARTITION"

    def test_low_global_gets_flat_partition(self):
        p = _make_partition(PartitionType.GLOBAL_STATEMENT, RiskLevel.LOW)
        agent = StrategyAgent()
        result = _run(agent.process([p]))
        assert result[0].metadata["strategy"] == "FLAT_PARTITION"

    def test_moderate_macro_definition_gets_macro_aware(self):
        p = _make_partition(PartitionType.MACRO_DEFINITION, RiskLevel.MODERATE)
        agent = StrategyAgent()
        result = _run(agent.process([p]))
        assert result[0].metadata["strategy"] == "MACRO_AWARE"

    def test_low_macro_invocation_gets_macro_aware(self):
        p = _make_partition(PartitionType.MACRO_INVOCATION, RiskLevel.LOW)
        agent = StrategyAgent()
        result = _run(agent.process([p]))
        assert result[0].metadata["strategy"] == "MACRO_AWARE"

    def test_sql_block_gets_dependency_preserving(self):
        p = _make_partition(PartitionType.SQL_BLOCK, RiskLevel.LOW)
        agent = StrategyAgent()
        result = _run(agent.process([p]))
        assert result[0].metadata["strategy"] == "DEPENDENCY_PRESERVING"

    def test_moderate_proc_gets_dependency_preserving(self):
        p = _make_partition(PartitionType.PROC_BLOCK, RiskLevel.MODERATE)
        agent = StrategyAgent()
        result = _run(agent.process([p]))
        assert result[0].metadata["strategy"] == "DEPENDENCY_PRESERVING"

    def test_conditional_block_gets_macro_aware(self):
        p = _make_partition(PartitionType.CONDITIONAL_BLOCK, RiskLevel.MODERATE)
        agent = StrategyAgent()
        result = _run(agent.process([p]))
        assert result[0].metadata["strategy"] == "MACRO_AWARE"

    def test_loop_block_gets_macro_aware(self):
        p = _make_partition(PartitionType.LOOP_BLOCK, RiskLevel.MODERATE)
        agent = StrategyAgent()
        result = _run(agent.process([p]))
        assert result[0].metadata["strategy"] == "MACRO_AWARE"


# ── Batch processing ──────────────────────────────────────────────────────────


class TestStrategyBatch:
    def test_all_blocks_get_strategy(self):
        blocks = [
            _make_partition(PartitionType.DATA_STEP, RiskLevel.LOW),
            _make_partition(PartitionType.MACRO_DEFINITION, RiskLevel.HIGH),
            _make_partition(PartitionType.SQL_BLOCK, RiskLevel.MODERATE),
            _make_partition(PartitionType.GLOBAL_STATEMENT, RiskLevel.LOW),
            _make_partition(PartitionType.PROC_BLOCK, RiskLevel.MODERATE),
        ]
        agent = StrategyAgent()
        result = _run(agent.process(blocks))
        assert len(result) == 5
        for r in result:
            assert "strategy" in r.metadata
            assert r.metadata["strategy"] in {
                "FLAT_PARTITION",
                "STRUCTURAL_GROUPING",
                "MACRO_AWARE",
                "DEPENDENCY_PRESERVING",
                "HUMAN_REVIEW",
            }

    def test_process_empty_list(self):
        agent = StrategyAgent()
        result = _run(agent.process([]))
        assert result == []

    def test_original_blocks_not_mutated_in_place(self):
        """process() should return new objects, not mutate the originals."""
        original = _make_partition(PartitionType.DATA_STEP, RiskLevel.LOW)
        dict(original.metadata)
        agent = StrategyAgent()
        result = _run(agent.process([original]))
        # The returned block must have strategy
        assert "strategy" in result[0].metadata
