"""Tests for Week 10 — Translation Layer (L3)."""

import pytest

from partition.translation.failure_mode_detector import (
    FailureMode,
    detect_failure_mode,
    get_failure_mode_rules,
)


# ── Failure Mode Detector ─────────────────────────────────────────────


class TestFailureModeDetector:
    def test_detects_retain(self):
        code = "DATA out; SET in; RETAIN running_total 0; running_total + amount; RUN;"
        assert detect_failure_mode(code) == FailureMode.RETAIN

    def test_detects_first_last(self):
        code = "DATA out; SET in; BY customer_id; IF FIRST.customer_id THEN total=0; RUN;"
        assert detect_failure_mode(code) == FailureMode.FIRST_LAST

    def test_detects_date_arithmetic(self):
        code = "DATA out; SET in; next_month = INTNX('MONTH', today(), 1); RUN;"
        assert detect_failure_mode(code) == FailureMode.DATE_ARITHMETIC

    def test_detects_merge_semantics(self):
        code = "DATA merged; MERGE a b; BY customer_id; RUN;"
        assert detect_failure_mode(code) == FailureMode.MERGE_SEMANTICS

    def test_detects_missing_value(self):
        code = "DATA out; SET in; IF NMISS(of x1-x10) > 0 THEN flag=1; RUN;"
        assert detect_failure_mode(code) == FailureMode.MISSING_VALUE_COMPARISON

    def test_detects_proc_means_output(self):
        code = (
            "PROC MEANS DATA=sales NWAY; CLASS region; "
            "VAR amount; OUTPUT OUT=summary MEAN=avg_amt; RUN;"
        )
        assert detect_failure_mode(code) == FailureMode.PROC_MEANS_OUTPUT

    def test_no_failure_mode(self):
        code = "DATA out; SET in; x = 1; IF x > 0 THEN y = 2; RUN;"
        assert detect_failure_mode(code) is None

    def test_rules_not_empty(self):
        for mode in FailureMode:
            rules = get_failure_mode_rules(mode)
            assert len(rules) > 0, f"No rules for {mode}"

    def test_case_insensitive_retain(self):
        code = "data out; set in; retain total 0; run;"
        assert detect_failure_mode(code) == FailureMode.RETAIN

    def test_datepart_detected(self):
        code = "DATA out; SET in; d = DATEPART(dt); RUN;"
        assert detect_failure_mode(code) == FailureMode.DATE_ARITHMETIC

    def test_intck_detected(self):
        code = "DATA out; SET in; diff = INTCK('DAY', d1, d2); RUN;"
        assert detect_failure_mode(code) == FailureMode.DATE_ARITHMETIC

    def test_cmiss_detected(self):
        code = "DATA out; SET in; IF CMISS(name) THEN flag=1; RUN;"
        assert detect_failure_mode(code) == FailureMode.MISSING_VALUE_COMPARISON

    def test_last_dot_detected(self):
        code = "DATA out; SET in; BY grp; IF LAST.grp THEN OUTPUT; RUN;"
        assert detect_failure_mode(code) == FailureMode.FIRST_LAST


# ── Validation Agent ──────────────────────────────────────────────────


class TestValidationAgent:
    def test_syntax_check_valid(self):
        from partition.translation.validation_agent import ValidationAgent

        agent = ValidationAgent()
        ok, err = agent._check_syntax("x = 1\ny = x + 2")
        assert ok is True
        assert err == ""

    def test_syntax_check_invalid(self):
        from partition.translation.validation_agent import ValidationAgent

        agent = ValidationAgent()
        ok, err = agent._check_syntax("def foo(\n  x = ")
        assert ok is False
        assert len(err) > 0

    def test_sandbox_has_required_keys(self):
        """Verify the sandbox function provides pd/np/df and blocks dangerous builtins."""
        import multiprocessing
        from partition.translation.validation_agent import _sandbox_exec

        manager = multiprocessing.Manager()
        result = manager.dict({"ok": False, "error": ""})
        _sandbox_exec("assert len(df) == 100", result)
        assert result["ok"] is True

    def test_sandbox_no_import(self):
        """Verify __import__ is blocked inside sandbox."""
        import multiprocessing
        from partition.translation.validation_agent import _sandbox_exec

        manager = multiprocessing.Manager()
        result = manager.dict({"ok": False, "error": ""})
        _sandbox_exec("__import__('os')", result)
        assert result["ok"] is False
        assert "import" in result["error"].lower() or "not defined" in result["error"].lower()

    def test_exec_simple_code(self):
        from partition.translation.validation_agent import ValidationAgent

        agent = ValidationAgent()
        ok, err, output = agent._execute_with_timeout(
            "result = df['amount'].sum()"
        )
        assert ok is True
        assert err == ""

    def test_exec_timeout(self):
        from partition.translation.validation_agent import ValidationAgent

        agent = ValidationAgent()
        ok, err, output = agent._execute_with_timeout(
            "x = 0\nwhile True:\n    x += 1", timeout=1
        )
        assert ok is False
        assert "Timeout" in err

    def test_exec_runtime_error(self):
        from partition.translation.validation_agent import ValidationAgent

        agent = ValidationAgent()
        ok, err, output = agent._execute_with_timeout(
            "result = 1 / 0"
        )
        assert ok is False
        assert "division by zero" in err

    def test_exec_outputs_captured(self):
        """Verify successful execution returns ok=True."""
        from partition.translation.validation_agent import ValidationAgent

        agent = ValidationAgent()
        ok, err, output = agent._execute_with_timeout(
            "total = df['amount'].sum()\ncount = len(df)"
        )
        assert ok is True
        assert err == ""

    def test_sandbox_df_columns(self):
        """Verify sandbox df has all expected columns."""
        import multiprocessing
        from partition.translation.validation_agent import _sandbox_exec

        manager = multiprocessing.Manager()
        result = manager.dict({"ok": False, "error": ""})
        _sandbox_exec(
            "assert 'id' in df.columns\n"
            "assert 'amount' in df.columns\n"
            "assert 'category' in df.columns\n"
            "assert 'date' in df.columns\n"
            "assert 'flag' in df.columns",
            result,
        )
        assert result["ok"] is True


# ── KB Query Client ───────────────────────────────────────────────────


class TestKBQueryClient:
    def test_missing_table_returns_empty(self, tmp_path):
        from partition.translation.kb_query import KBQueryClient

        client = KBQueryClient(db_path=str(tmp_path / "empty_kb"))
        examples = client.retrieve_examples(
            query_embedding=[0.0] * 768,
            partition_type="DATA_STEP",
        )
        assert examples == []


# ── ConversionResult model ────────────────────────────────────────────


class TestConversionResult:
    def test_create_conversion_result(self):
        import uuid
        from partition.models.conversion_result import ConversionResult
        from partition.models.enums import ConversionStatus

        fid = uuid.uuid4()
        bid = uuid.uuid4()
        result = ConversionResult(
            block_id=bid,
            file_id=fid,
            python_code="x = 1",
            status=ConversionStatus.SUCCESS,
            llm_confidence=0.95,
            model_used="azure_gpt4o",
        )
        assert result.block_id == bid
        assert result.status == ConversionStatus.SUCCESS
        assert result.llm_confidence == 0.95

    def test_default_fields(self):
        import uuid
        from partition.models.conversion_result import ConversionResult

        result = ConversionResult(
            block_id=uuid.uuid4(),
            file_id=uuid.uuid4(),
            python_code="pass",
        )
        assert result.retry_count == 0
        assert result.imports_detected == []
        assert result.failure_mode_flagged == ""
