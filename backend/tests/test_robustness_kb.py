"""Tests for Week 9: Robustness + Knowledge Base Generation.

Covers:
    - RateLimitSemaphore — concurrency control
    - CircuitBreaker     — failure detection + auto-reset
    - detect_file_size_strategy — standard / large / huge
    - checkpoint_interval       — block intervals per strategy
    - MemoryMonitor             — RSS tracking (psutil)
    - configure_memory_guards   — env-var setup
    - KBWriter                  — LanceDB insert / count / coverage
    - kb_changelog              — DuckDB mutation logging
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time

import pytest
from partition.kb.kb_changelog import get_history, log_kb_change
from partition.utils.large_file import (
    HUGE_FILE_LINE_THRESHOLD,
    LARGE_FILE_LINE_THRESHOLD,
    MemoryMonitor,
    checkpoint_interval,
    configure_memory_guards,
    detect_file_size_strategy,
)
from partition.utils.retry import (
    CircuitBreaker,
    RateLimitSemaphore,
    azure_breaker,
    azure_limiter,
    groq_breaker,
    groq_limiter,
)

# =====================================================================
# Helpers
# =====================================================================


def _write_temp_file(line_count: int) -> str:
    """Create a temp file with the given number of lines."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".sas", delete=False, encoding="utf-8")
    for i in range(line_count):
        tmp.write(f"/* line {i} */\n")
    tmp.close()
    return tmp.name


# =====================================================================
# RateLimitSemaphore
# =====================================================================


class TestRateLimitSemaphore:
    """Tests for the async concurrency semaphore."""

    def test_default_max_concurrent(self):
        limiter = RateLimitSemaphore()
        assert limiter._max == 10

    def test_custom_max_concurrent(self):
        limiter = RateLimitSemaphore(max_concurrent=3)
        assert limiter._max == 3

    @pytest.mark.asyncio
    async def test_acquire_release(self):
        limiter = RateLimitSemaphore(max_concurrent=2)
        assert limiter.active_calls == 0
        async with limiter:
            assert limiter.active_calls == 1
        assert limiter.active_calls == 0

    @pytest.mark.asyncio
    async def test_concurrent_limit(self):
        """Verify that only max_concurrent tasks run simultaneously."""
        limiter = RateLimitSemaphore(max_concurrent=2)
        peak = 0

        async def worker():
            nonlocal peak
            async with limiter:
                peak = max(peak, limiter.active_calls)
                await asyncio.sleep(0.05)

        await asyncio.gather(*[worker() for _ in range(5)])
        assert peak <= 2

    def test_global_instances_exist(self):
        """Ensure global rate limiters are configured."""
        assert azure_limiter._max == 10
        assert groq_limiter._max == 3


# =====================================================================
# CircuitBreaker
# =====================================================================


class TestCircuitBreaker:
    """Tests for the circuit breaker pattern."""

    def test_initial_state_closed(self):
        cb = CircuitBreaker(failure_threshold=3, name="test")
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.allow_request() is True

    def test_trip_open_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, name="test")
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        assert cb.allow_request() is False

    def test_success_resets_failures(self):
        cb = CircuitBreaker(failure_threshold=3, name="test")
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb._failure_count == 0

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.1, name="test")
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        # Wait for reset timeout
        time.sleep(0.15)
        assert cb.state == CircuitBreaker.HALF_OPEN
        assert cb.allow_request() is True

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.05, name="test")
        cb.record_failure()
        time.sleep(0.1)
        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0.05, name="test")
        cb.record_failure()
        time.sleep(0.1)
        assert cb.state == CircuitBreaker.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    def test_manual_reset(self):
        cb = CircuitBreaker(failure_threshold=1, name="test")
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        cb.reset()
        assert cb.state == CircuitBreaker.CLOSED

    def test_global_breakers_exist(self):
        """Ensure global circuit breakers are configured."""
        assert azure_breaker.failure_threshold == 5
        assert azure_breaker.reset_timeout == 60.0
        assert groq_breaker.failure_threshold == 3
        assert groq_breaker.reset_timeout == 120.0


# =====================================================================
# detect_file_size_strategy
# =====================================================================


class TestFileSizeStrategy:
    """Tests for file-size detection and strategy selection."""

    def test_standard_file(self):
        path = _write_temp_file(100)
        try:
            assert detect_file_size_strategy(path) == "standard"
        finally:
            os.unlink(path)

    def test_large_file(self):
        path = _write_temp_file(LARGE_FILE_LINE_THRESHOLD + 1)
        try:
            assert detect_file_size_strategy(path) == "large"
        finally:
            os.unlink(path)

    def test_huge_file(self):
        path = _write_temp_file(HUGE_FILE_LINE_THRESHOLD + 1)
        try:
            assert detect_file_size_strategy(path) == "huge"
        finally:
            os.unlink(path)

    def test_nonexistent_file_returns_standard(self):
        assert detect_file_size_strategy("/nonexistent/file.sas") == "standard"

    def test_boundary_standard(self):
        """Exactly at LARGE threshold → still standard."""
        path = _write_temp_file(LARGE_FILE_LINE_THRESHOLD)
        try:
            assert detect_file_size_strategy(path) == "standard"
        finally:
            os.unlink(path)


class TestCheckpointInterval:
    def test_standard(self):
        assert checkpoint_interval("standard") == 50

    def test_large(self):
        assert checkpoint_interval("large") == 25

    def test_huge(self):
        assert checkpoint_interval("huge") == 10

    def test_unknown_defaults(self):
        assert checkpoint_interval("unknown") == 50


# =====================================================================
# MemoryMonitor
# =====================================================================


class TestMemoryMonitor:
    """Tests for psutil-based memory monitoring."""

    def test_initial_peak(self):
        mon = MemoryMonitor()
        assert mon.peak_mb == 0.0

    def test_check_returns_float(self):
        mon = MemoryMonitor()
        result = mon.check()
        assert isinstance(result, float)
        # If psutil is available, RSS should be > 0
        if mon._psutil_available:
            assert result > 0
            assert mon.peak_mb > 0

    def test_assert_under_limit_high_threshold(self):
        mon = MemoryMonitor()
        # 10 GB limit — should always be under
        assert mon.assert_under_limit(10_000) is True

    def test_assert_under_limit_tiny(self):
        mon = MemoryMonitor()
        if mon._psutil_available:
            # 0.001 MB limit — any real process exceeds this
            assert mon.assert_under_limit(0.001) is False


# =====================================================================
# configure_memory_guards
# =====================================================================


class TestMemoryGuards:
    def test_sets_env_vars(self):
        # Clear vars first
        os.environ.pop("PYTORCH_CUDA_ALLOC_CONF", None)
        os.environ.pop("OMP_NUM_THREADS", None)

        configure_memory_guards()

        assert os.environ.get("PYTORCH_CUDA_ALLOC_CONF") == "max_split_size_mb:128"
        assert os.environ.get("OMP_NUM_THREADS") == "4"

    def test_does_not_overwrite(self):
        os.environ["OMP_NUM_THREADS"] = "8"
        configure_memory_guards()
        assert os.environ.get("OMP_NUM_THREADS") == "8"
        # Cleanup
        os.environ.pop("OMP_NUM_THREADS", None)


# =====================================================================
# KB Changelog (DuckDB)
# =====================================================================


class TestKBChangelog:
    """Tests for the DuckDB KB changelog logger."""

    @pytest.fixture
    def db_path(self, tmp_path):
        return str(tmp_path / "test_changelog.duckdb")

    def test_log_insert(self, db_path):
        change_id = log_kb_change(
            db_path=db_path,
            example_id="ex-001",
            action="insert",
            new_version=1,
            author="test",
        )
        assert change_id  # non-empty UUID string

    def test_log_and_retrieve(self, db_path):
        log_kb_change(
            db_path=db_path,
            example_id="ex-002",
            action="insert",
            new_version=1,
            author="test_suite",
            diff_summary="Initial insert",
        )
        history = get_history(db_path, "ex-002")
        assert len(history) == 1
        assert history[0]["action"] == "insert"
        assert history[0]["new_version"] == 1
        assert history[0]["author"] == "test_suite"

    def test_multiple_versions(self, db_path):
        log_kb_change(
            db_path=db_path,
            example_id="ex-003",
            action="insert",
            new_version=1,
            author="gen",
        )
        log_kb_change(
            db_path=db_path,
            example_id="ex-003",
            action="update",
            old_version=1,
            new_version=2,
            author="reviewer",
            diff_summary="Fixed date conversion",
        )
        log_kb_change(
            db_path=db_path,
            example_id="ex-003",
            action="rollback",
            old_version=2,
            new_version=1,
            author="rollback_script",
            diff_summary="Rolled back v2→v1",
        )
        history = get_history(db_path, "ex-003")
        assert len(history) == 3
        assert [h["action"] for h in history] == ["insert", "update", "rollback"]

    def test_different_examples_isolated(self, db_path):
        log_kb_change(
            db_path=db_path,
            example_id="a",
            action="insert",
            new_version=1,
            author="t",
        )
        log_kb_change(
            db_path=db_path,
            example_id="b",
            action="insert",
            new_version=1,
            author="t",
        )
        assert len(get_history(db_path, "a")) == 1
        assert len(get_history(db_path, "b")) == 1
        assert len(get_history(db_path, "c")) == 0


# =====================================================================
# KBWriter (LanceDB) — integration tests with tmp directory
# =====================================================================


class TestKBWriter:
    """Tests for the LanceDB KB writer.

    These use a temporary directory as the LanceDB store.
    """

    @pytest.fixture
    def writer(self, tmp_path):
        from partition.kb.kb_writer import KBWriter

        return KBWriter(db_path=str(tmp_path / "test_lancedb"))

    def _make_pair(self, category: str = "DATA_STEP_BASIC", version: int = 1) -> dict:
        import uuid

        return {
            "example_id": str(uuid.uuid4()),
            "sas_code": "DATA test; SET input; RUN;",
            "python_code": "df = pd.read_csv('input.csv')",
            "embedding": [0.1] * 768,
            "partition_type": category,
            "complexity_tier": "LOW",
            "target_runtime": "python",
            "verified": True,
            "source": "test",
            "failure_mode": "",
            "verification_method": "manual",
            "verification_score": 0.95,
            "category": category,
            "version": version,
            "superseded_by": None,
            "created_at": "2025-01-01T00:00:00",
        }

    def test_empty_count(self, writer):
        assert writer.count() == 0

    def test_insert_and_count(self, writer):
        pairs = [self._make_pair() for _ in range(5)]
        inserted = writer.insert_pairs(pairs)
        assert inserted == 5
        assert writer.count() == 5

    def test_insert_empty_list(self, writer):
        assert writer.insert_pairs([]) == 0

    def test_coverage_stats(self, writer):
        pairs = [
            self._make_pair("DATA_STEP_BASIC"),
            self._make_pair("DATA_STEP_BASIC"),
            self._make_pair("PROC_SQL"),
        ]
        writer.insert_pairs(pairs)
        stats = writer.coverage_stats()
        assert stats["DATA_STEP_BASIC"] == 2
        assert stats["PROC_SQL"] == 1

    def test_append_to_existing(self, writer):
        writer.insert_pairs([self._make_pair()])
        writer.insert_pairs([self._make_pair(), self._make_pair()])
        assert writer.count() == 3

    def test_empty_coverage_before_insert(self, writer):
        assert writer.coverage_stats() == {}
