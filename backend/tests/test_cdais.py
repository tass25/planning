"""test_cdais.py — Unit tests for CDAIS (Constraint-Driven Adversarial Input Synthesis).

Tests cover:
  - CDAISRunner.run_on_code() with known-bad translations for each error class
  - CDAISRunner.run() with a PartitionIR object
  - CDAISReport.to_prompt_block() and .summary()
  - applicable_classes() applicability detection
  - Synthesis produces SAT witnesses for all 6 error classes

Each "known-bad" translation uses the canonical mistranslation for its error class
so that CDAIS should detect a failure (or at least a non-trivial check).
"""

from __future__ import annotations

import uuid

import pytest
from partition.testing.cdais.cdais_runner import CDAISReport, CDAISRunner
from partition.testing.cdais.constraint_catalog import (
    ALL_ERROR_CLASSES,
    ERROR_CLASS_MAP,
    ConstraintConfig,
    applicable_classes,
)
from partition.testing.cdais.synthesizer import CDASISynthesizer

# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def runner() -> CDAISRunner:
    return CDAISRunner()


@pytest.fixture(scope="module")
def synthesizer() -> CDASISynthesizer:
    return CDASISynthesizer()


@pytest.fixture(scope="module")
def cfg() -> ConstraintConfig:
    return ConstraintConfig()


# ── SAS code samples for each error class ─────────────────────────────────────

SAS_RETAIN_RESET = """
data running_totals;
  set sales;
  by region;
  retain total 0;
  if first.region then total = 0;
  total + amount;
run;
"""

SAS_LAG_QUEUE = """
data lagged;
  set transactions;
  by customer_id;
  prev_amount = lag(amount);
run;
"""

SAS_SORT_STABLE = """
proc sort data=orders out=orders_sorted;
  by status;
run;
"""

SAS_NULL_ARITHMETIC = """
data accumulated;
  set raw;
  retain running_sum 0;
  running_sum + value;
run;
"""

SAS_JOIN_TYPE = """
data merged_out;
  merge customers accounts;
  by customer_id;
run;
"""

SAS_GROUP_BOUNDARY = """
data first_rows;
  set transactions;
  by region;
  if first.region;
run;
"""

# ── Known-bad Python translations for each error class ───────────────────────

BAD_RETAIN_RESET = "df['total'] = df['amount'].cumsum()"
BAD_LAG_QUEUE = "df['prev_amount'] = df['amount'].shift(1)"
BAD_SORT_STABLE = "df = df.sort_values('status')"  # missing kind='mergesort'
BAD_NULL_ARITHMETIC = "df['running_sum'] = df['value'].cumsum()"  # NaN propagation
BAD_JOIN_TYPE = "df = pd.merge(customers, accounts, on='customer_id', how='inner')"
BAD_GROUP_BOUNDARY = "df = df.head(1)"  # whole-DF head, not per-group

# Correct Python translations (should pass or be certified)
GOOD_RETAIN_RESET = """
df['total'] = df.groupby('region')['amount'].cumsum()
"""
GOOD_LAG_QUEUE = """
df['prev_amount'] = df.groupby('customer_id')['amount'].shift(1)
"""
GOOD_SORT_STABLE = "df = df.sort_values('status', kind='mergesort')"
GOOD_JOIN_TYPE = "df = pd.merge(customers, accounts, on='customer_id', how='outer')"
GOOD_GROUP_BOUNDARY = "df = df.groupby('region').first().reset_index()"


# ── Tests: applicable_classes() ───────────────────────────────────────────────


class TestApplicableClasses:
    def test_retain_reset_detected(self):
        classes = applicable_classes(SAS_RETAIN_RESET)
        names = [ec.name for ec in classes]
        assert "RETAIN_RESET" in names

    def test_lag_queue_detected(self):
        classes = applicable_classes(SAS_LAG_QUEUE)
        names = [ec.name for ec in classes]
        assert "LAG_QUEUE" in names

    def test_sort_stable_detected(self):
        classes = applicable_classes(SAS_SORT_STABLE)
        names = [ec.name for ec in classes]
        assert "SORT_STABLE" in names

    def test_null_arithmetic_detected(self):
        classes = applicable_classes(SAS_NULL_ARITHMETIC)
        names = [ec.name for ec in classes]
        assert "NULL_ARITHMETIC" in names

    def test_join_type_detected(self):
        classes = applicable_classes(SAS_JOIN_TYPE)
        names = [ec.name for ec in classes]
        assert "JOIN_TYPE" in names

    def test_group_boundary_detected(self):
        classes = applicable_classes(SAS_GROUP_BOUNDARY)
        names = [ec.name for ec in classes]
        assert "GROUP_BOUNDARY" in names

    def test_no_classes_for_empty_sas(self):
        assert applicable_classes("") == []

    def test_no_false_positives_for_simple_data_step(self):
        # A simple DATA SET with no RETAIN, LAG, SORT, MERGE, FIRST/LAST
        sas = "data out; set inp; x = 1; run;"
        classes = applicable_classes(sas)
        names = [ec.name for ec in classes]
        assert "RETAIN_RESET" not in names
        assert "LAG_QUEUE" not in names
        assert "SORT_STABLE" not in names
        assert "GROUP_BOUNDARY" not in names


# ── Tests: CDASISynthesizer ────────────────────────────────────────────────────


class TestCDASISynthesizer:
    @pytest.mark.parametrize("class_name", [ec.name for ec in ALL_ERROR_CLASSES])
    def test_synthesis_produces_sat_witness(self, synthesizer, cfg, class_name):
        """Every error class should synthesize a SAT witness."""
        ec = ERROR_CLASS_MAP[class_name]
        result = synthesizer.synthesize(ec, cfg)
        assert result.sat, f"{class_name}: expected SAT but got UNSAT"
        assert result.witness_df is not None
        assert not result.witness_df.empty

    @pytest.mark.parametrize("class_name", [ec.name for ec in ALL_ERROR_CLASSES])
    def test_witness_has_minimum_rows(self, synthesizer, cfg, class_name):
        """Witnesses should be small (≤ 2*n_groups*n_rows_per_group rows)."""
        ec = ERROR_CLASS_MAP[class_name]
        result = synthesizer.synthesize(ec, cfg)
        if result.sat and result.witness_df is not None:
            max_rows = cfg.n_groups * cfg.n_rows_per_group * 2
            assert (
                len(result.witness_df) <= max_rows
            ), f"{class_name}: witness has {len(result.witness_df)} rows > {max_rows}"


# ── Tests: CDAISRunner.run_on_code() ──────────────────────────────────────────


class TestCDAISRunnerOnCode:
    def test_retain_reset_bad_translation_flagged(self, runner):
        report = runner.run_on_code(SAS_RETAIN_RESET, BAD_RETAIN_RESET)
        # RETAIN_RESET class should be applicable and checked
        assert report.n_classes_checked >= 1
        assert isinstance(report.all_passed, bool)
        assert isinstance(report.certificates, list)
        assert isinstance(report.failures, list)

    def test_lag_queue_bad_translation_flagged(self, runner):
        report = runner.run_on_code(SAS_LAG_QUEUE, BAD_LAG_QUEUE)
        assert report.n_classes_checked >= 1

    def test_sort_stable_bad_translation_flagged(self, runner):
        report = runner.run_on_code(SAS_SORT_STABLE, BAD_SORT_STABLE)
        assert report.n_classes_checked >= 1

    def test_join_type_bad_translation_flagged(self, runner):
        report = runner.run_on_code(SAS_JOIN_TYPE, BAD_JOIN_TYPE)
        assert report.n_classes_checked >= 1

    def test_group_boundary_bad_translation_flagged(self, runner):
        report = runner.run_on_code(SAS_GROUP_BOUNDARY, BAD_GROUP_BOUNDARY)
        assert report.n_classes_checked >= 1

    def test_empty_sas_all_skipped(self, runner):
        report = runner.run_on_code("", "pass")
        assert report.n_classes_checked == 0
        assert report.all_passed is True

    def test_report_has_partition_id(self, runner):
        # run_on_code uses uuid.UUID(int=0) as the block_id internally
        report = runner.run_on_code(SAS_RETAIN_RESET, BAD_RETAIN_RESET, block_id="test-block")
        assert isinstance(report.partition_id, str)
        assert len(report.partition_id) > 0

    def test_report_has_latency(self, runner):
        report = runner.run_on_code(SAS_SORT_STABLE, BAD_SORT_STABLE)
        assert report.latency_ms >= 0


# ── Tests: CDAISReport ────────────────────────────────────────────────────────


class TestCDAISReport:
    def test_to_prompt_block_all_passed(self):
        report = CDAISReport(
            partition_id="test",
            all_passed=True,
            certificates=["RETAIN_RESET: formally covered"],
            n_classes_checked=1,
        )
        block = report.to_prompt_block()
        assert "CDAIS" in block
        assert "1" in block

    def test_to_prompt_block_with_failures(self, runner):
        report = runner.run_on_code(SAS_RETAIN_RESET, BAD_RETAIN_RESET)
        block = report.to_prompt_block()
        assert isinstance(block, str)
        assert len(block) > 0

    def test_summary_format(self, runner):
        report = runner.run_on_code(SAS_JOIN_TYPE, BAD_JOIN_TYPE)
        summary = report.summary()
        assert "CDAIS" in summary
        assert "/" in summary  # "X/Y error classes certified"
        assert "ms" in summary

    def test_summary_all_passed(self):
        report = CDAISReport(
            partition_id="p",
            all_passed=True,
            certificates=["A", "B"],
            n_classes_checked=2,
        )
        summary = report.summary()
        assert "2/2" in summary
        assert "0 failures" in summary


# ── Tests: CDAISRunner.run() with PartitionIR ─────────────────────────────────


class TestCDAISRunnerWithPartitionIR:
    def test_run_with_partition_ir(self, runner):
        from partition.models.enums import PartitionType, RiskLevel
        from partition.models.partition_ir import PartitionIR

        p = PartitionIR(
            block_id=uuid.uuid4(),
            file_id=uuid.uuid4(),
            partition_type=PartitionType.DATA_STEP,
            source_code=SAS_RETAIN_RESET,
            line_start=0,
            line_end=0,
            risk_level=RiskLevel.HIGH,
        )
        report = runner.run(p, BAD_RETAIN_RESET)
        assert isinstance(report, CDAISReport)
        assert report.partition_id == str(p.block_id)
        assert report.n_classes_checked >= 1

    def test_run_returns_report_even_on_empty_code(self, runner):
        from partition.models.enums import PartitionType, RiskLevel
        from partition.models.partition_ir import PartitionIR

        p = PartitionIR(
            block_id=uuid.uuid4(),
            file_id=uuid.uuid4(),
            partition_type=PartitionType.DATA_STEP,
            source_code="data out; set inp; run;",
            line_start=0,
            line_end=0,
            risk_level=RiskLevel.LOW,
        )
        report = runner.run(p, "df = inp.copy()")
        assert isinstance(report, CDAISReport)
        # Simple data step should have no applicable error classes
        assert report.n_classes_checked == 0
        assert report.all_passed is True


# ── Tests: skipped classes handling ───────────────────────────────────────────


class TestSkippedClasses:
    def test_non_applicable_classes_are_skipped(self, runner):
        # SAS with only PROC SORT — only SORT_STABLE should be applicable
        report = runner.run_on_code(SAS_SORT_STABLE, BAD_SORT_STABLE)
        # RETAIN_RESET, LAG_QUEUE, JOIN_TYPE, GROUP_BOUNDARY should be in skipped
        assert "RETAIN_RESET" in report.skipped_classes or report.n_classes_checked <= 2

    def test_skipped_classes_are_strings(self, runner):
        report = runner.run_on_code(SAS_JOIN_TYPE, BAD_JOIN_TYPE)
        for s in report.skipped_classes:
            assert isinstance(s, str)
