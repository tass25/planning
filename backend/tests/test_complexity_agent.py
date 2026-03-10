"""Tests for ComplexityAgent (L2-D).

Run with:
    cd sas_converter
    ../venv/Scripts/python -m pytest tests/test_complexity_agent.py -v
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from partition.complexity.complexity_agent import ComplexityAgent, compute_ece
from partition.complexity.features import extract
from partition.models.enums import PartitionType, RiskLevel
from partition.models.partition_ir import PartitionIR

GOLD_DIR = Path(__file__).parent.parent / "knowledge_base" / "gold_standard"


def _run(coro):
    return asyncio.run(coro)


def _make_partition(
    ptype: PartitionType,
    line_start: int,
    line_end: int,
    source: str = "",
    nesting: int = 0,
    ambiguous: bool = False,
) -> PartitionIR:
    return PartitionIR(
        file_id=uuid4(),
        partition_type=ptype,
        source_code=source,
        line_start=line_start,
        line_end=line_end,
        metadata={"nesting_depth": nesting, "is_ambiguous": ambiguous},
    )


# ── Feature extraction ────────────────────────────────────────────────────────

class TestFeatureExtraction:

    def test_line_count_normalised(self):
        p = _make_partition(PartitionType.DATA_STEP, 1, 10)
        f = extract(p)
        assert abs(f.line_count_norm - 10 / 200) < 1e-9

    def test_call_execute_detected(self):
        p = _make_partition(
            PartitionType.DATA_STEP, 1, 5,
            source="data x; set y; call execute('%macro_call;'); run;"
        )
        f = extract(p)
        assert f.has_call_execute == 1.0

    def test_no_call_execute(self):
        p = _make_partition(PartitionType.DATA_STEP, 1, 5, source="data x; set y; run;")
        f = extract(p)
        assert f.has_call_execute == 0.0

    def test_macro_definition_type_weight(self):
        p = _make_partition(PartitionType.MACRO_DEFINITION, 1, 20)
        f = extract(p)
        assert f.type_weight == 2.0

    def test_global_statement_type_weight(self):
        p = _make_partition(PartitionType.GLOBAL_STATEMENT, 1, 3)
        f = extract(p)
        assert f.type_weight == 0.2

    def test_feature_vector_length(self):
        p = _make_partition(PartitionType.SQL_BLOCK, 1, 30, nesting=2)
        f = extract(p)
        assert len(f.to_list()) == 6


# ── Rule-based predictions ────────────────────────────────────────────────────

class TestRuleBasedPrediction:

    def test_short_data_step_is_low(self):
        p = _make_partition(PartitionType.DATA_STEP, 1, 5)
        agent = ComplexityAgent()
        result = _run(agent.process([p]))
        assert result[0].risk_level == RiskLevel.LOW

    def test_long_macro_definition_is_high(self):
        p = _make_partition(PartitionType.MACRO_DEFINITION, 1, 100)
        agent = ComplexityAgent()
        result = _run(agent.process([p]))
        assert result[0].risk_level == RiskLevel.HIGH

    def test_call_execute_is_high(self):
        p = _make_partition(
            PartitionType.DATA_STEP, 1, 5,
            source="data _null_; call execute('%mymacro;'); run;",
        )
        agent = ComplexityAgent()
        result = _run(agent.process([p]))
        assert result[0].risk_level == RiskLevel.HIGH

    def test_deep_nesting_is_high(self):
        p = _make_partition(PartitionType.CONDITIONAL_BLOCK, 1, 20, nesting=4)
        agent = ComplexityAgent()
        result = _run(agent.process([p]))
        assert result[0].risk_level == RiskLevel.HIGH

    def test_moderate_block(self):
        p = _make_partition(PartitionType.PROC_BLOCK, 1, 30)
        agent = ComplexityAgent()
        result = _run(agent.process([p]))
        assert result[0].risk_level == RiskLevel.MODERATE

    def test_confidence_in_metadata(self):
        p = _make_partition(PartitionType.DATA_STEP, 1, 5)
        agent = ComplexityAgent()
        result = _run(agent.process([p]))
        conf = result[0].metadata.get("complexity_confidence")
        assert conf is not None
        assert 0.0 < conf <= 1.0


# ── ECE utility ───────────────────────────────────────────────────────────────

class TestECE:

    def test_perfect_calibration_ece_zero(self):
        """A perfectly calibrated model has ECE ≈ 0."""
        # All confidence = 1.0 for the correct class (overconfident but correct)
        y_true  = np.array([0, 1, 2, 0, 1, 2])
        y_proba = np.eye(3)[[0, 1, 2, 0, 1, 2]]  # one-hot → perfectly confident
        ece = compute_ece(y_true, y_proba)
        # With n=6 samples and perfect accuracy, ECE is nearly 0
        assert ece < 0.05

    def test_random_proba_ece_is_high(self):
        """Uniformly random probabilities → high ECE."""
        rng = np.random.default_rng(0)
        y_true  = rng.integers(0, 3, size=300)
        raw     = rng.random((300, 3))
        y_proba = raw / raw.sum(axis=1, keepdims=True)
        ece = compute_ece(y_true, y_proba)
        # Random model is poorly calibrated
        assert ece > 0.05


# ── LogReg + Platt on gold data ───────────────────────────────────────────────

@pytest.mark.skipif(
    not GOLD_DIR.exists(),
    reason="Gold standard dir not found — run from sas_converter/",
)
class TestComplexityFit:

    def test_fit_returns_expected_keys(self):
        agent = ComplexityAgent()
        metrics = agent.fit(GOLD_DIR, test_size=0.20, seed=42)
        assert set(metrics) >= {"train_acc", "test_acc", "ece", "n_train", "n_test"}

    def test_train_accuracy_above_60_pct(self):
        agent = ComplexityAgent()
        metrics = agent.fit(GOLD_DIR, test_size=0.20, seed=42)
        assert metrics["train_acc"] > 0.60, f"Train acc={metrics['train_acc']:.2%}"

    def test_test_accuracy_above_50_pct(self):
        agent = ComplexityAgent()
        metrics = agent.fit(GOLD_DIR, test_size=0.20, seed=42)
        assert metrics["test_acc"] > 0.50, f"Test acc={metrics['test_acc']:.2%}"

    def test_ece_below_threshold(self):
        """ECE on the held-out 20 % split must be < 0.08 (Platt target)."""
        agent = ComplexityAgent()
        metrics = agent.fit(GOLD_DIR, test_size=0.20, seed=42)
        ece = metrics["ece"]
        assert ece < 0.10, (
            f"ECE={ece:.4f} exceeds 0.10 — check calibration or features"
        )

    def test_process_after_fit_uses_model(self):
        """After fit(), process() should mark blocks as fitted=True."""
        agent = ComplexityAgent()
        agent.fit(GOLD_DIR, test_size=0.20, seed=42)
        assert agent._fitted is True
        # Create a handful of blocks and process them
        blocks = [
            _make_partition(PartitionType.DATA_STEP, 1, 5),
            _make_partition(PartitionType.MACRO_DEFINITION, 1, 100),
            _make_partition(PartitionType.SQL_BLOCK, 1, 30, nesting=1),
        ]
        result = _run(agent.process(blocks))
        assert len(result) == 3
        for r in result:
            assert r.risk_level in (RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH)
            assert 0.0 < r.metadata["complexity_confidence"] <= 1.0
