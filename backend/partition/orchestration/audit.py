"""LLM audit logger -- logs every LLM call to DuckDB.

All LLM invocations are recorded in the ``llm_audit`` DuckDB table for
local analytics, calibration, and ablation tracking.

Usage as a context manager::

    audit = LLMAuditLogger("data/analytics.duckdb")
    with audit.log_call("BoundaryDetectorAgent", "gpt-5.4-mini", prompt) as call:
        result = llm_client.generate(prompt)
        call.set_response(result)
"""

from __future__ import annotations

import hashlib
import time
import uuid
from contextlib import contextmanager
from typing import Optional

import duckdb
import structlog

from partition.orchestration.telemetry import track_metric

logger = structlog.get_logger()

# Cost per 1M tokens (input, output) — update when pricing changes
_COST_TABLE: dict[str, tuple[float, float]] = {
    "gpt-5.4-mini": (0.15, 0.60),
    "llama-3.3-70b-versatile": (0.0, 0.0),
    "minimax-m2.7:cloud": (0.0, 0.0),
    "nemotron-3-super:cloud": (0.0, 0.0),
    "qwen3-coder-next": (0.0, 0.0),
    "gemini-2.0-flash": (0.0, 0.0),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate USD cost for an LLM call based on token counts."""
    rates = _COST_TABLE.get(model, (0.0, 0.0))
    return (prompt_tokens * rates[0] + completion_tokens * rates[1]) / 1_000_000


# Module-level DuckDB connection cache (one per db_path).
_duckdb_connections: dict[str, duckdb.DuckDBPyConnection] = {}


def _get_duckdb(db_path: str) -> duckdb.DuckDBPyConnection:
    """Return a cached DuckDB connection (singleton per path).

    Auto-creates the ``llm_audit`` table if it does not exist.
    """
    if db_path not in _duckdb_connections:
        try:
            conn = duckdb.connect(db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_audit (
                    call_id          VARCHAR,
                    agent_name       VARCHAR,
                    model_name       VARCHAR,
                    prompt_hash      VARCHAR,
                    response_hash    VARCHAR,
                    latency_ms       DOUBLE,
                    success          BOOLEAN,
                    error_msg        VARCHAR,
                    tier             VARCHAR,
                    prompt_tokens    INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    estimated_cost   DOUBLE DEFAULT 0.0,
                    failure_mode     VARCHAR DEFAULT '',
                    created_at       TIMESTAMP DEFAULT NOW()
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversion_results (
                    conversion_id        VARCHAR,
                    block_id             VARCHAR,
                    file_id              VARCHAR,
                    python_code          VARCHAR,
                    imports_detected     VARCHAR,
                    status               VARCHAR,
                    llm_confidence       DOUBLE,
                    failure_mode_flagged VARCHAR,
                    model_used           VARCHAR,
                    kb_examples_used     VARCHAR,
                    retry_count          INTEGER,
                    trace_id             VARCHAR
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kb_changelog (
                    changelog_id  VARCHAR,
                    example_id    VARCHAR,
                    action        VARCHAR,
                    changed_by    VARCHAR,
                    description   VARCHAR,
                    created_at    TIMESTAMP DEFAULT NOW()
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS failure_mode_accuracy (
                    run_id           VARCHAR,
                    failure_mode     VARCHAR,
                    total            INTEGER,
                    succeeded        INTEGER,
                    accuracy         DOUBLE,
                    created_at       TIMESTAMP DEFAULT NOW()
                )
            """)
            _duckdb_connections[db_path] = conn
        except Exception as exc:
            logger.warning("duckdb_init_failed", db_path=db_path, error=str(exc))
            raise
    return _duckdb_connections[db_path]


class LLMAuditLogger:
    """Thin wrapper around DuckDB ``llm_audit`` inserts."""

    def __init__(self, db_path: str = "data/analytics.duckdb"):
        self.db_path = db_path

    @contextmanager
    def log_call(
        self,
        agent_name: str,
        model_name: str,
        prompt: str,
        tier: Optional[str] = None,
    ):
        """Context manager that times and persists an LLM invocation."""
        call = _LLMCallTracker(
            db_path=self.db_path,
            agent_name=agent_name,
            model_name=model_name,
            prompt=prompt,
            tier=tier,
        )
        call.start()
        try:
            yield call
            call.succeed()
        except Exception as exc:
            call.fail(str(exc))
            raise
        finally:
            call.persist()

    def log_failure_mode_accuracy(
        self,
        run_id: str,
        results: list[dict],
    ) -> None:
        """Compute and persist per-failure-mode translation accuracy.

        Args:
            run_id: Pipeline run identifier.
            results: List of ConversionResult dicts with 'failure_mode_flagged' and 'status'.
        """
        from collections import Counter

        mode_total: Counter[str] = Counter()
        mode_success: Counter[str] = Counter()
        for r in results:
            fm = r.get("failure_mode_flagged", "")
            if not fm:
                continue
            mode_total[fm] += 1
            if r.get("status") in ("SUCCESS", "success"):
                mode_success[fm] += 1

        if not mode_total:
            return

        try:
            con = _get_duckdb(self.db_path)
            for fm, total in mode_total.items():
                succeeded = mode_success.get(fm, 0)
                accuracy = succeeded / total if total else 0.0
                con.execute(
                    "INSERT INTO failure_mode_accuracy VALUES (?, ?, ?, ?, ?, NOW())",
                    [run_id, fm, total, succeeded, accuracy],
                )
                track_metric(
                    "failure_mode_accuracy",
                    accuracy,
                    {"failure_mode": fm, "run_id": run_id},
                )
            logger.info(
                "failure_mode_accuracy_logged",
                run_id=run_id,
                modes={fm: f"{mode_success.get(fm, 0)}/{t}" for fm, t in mode_total.items()},
            )
        except Exception as exc:
            logger.warning("failure_mode_accuracy_failed", error=str(exc))


class _LLMCallTracker:
    """Internal tracker created per ``log_call`` invocation."""

    def __init__(
        self,
        db_path: str,
        agent_name: str,
        model_name: str,
        prompt: str,
        tier: Optional[str],
    ):
        self.db_path = db_path
        self.call_id = str(uuid.uuid4())
        self.agent_name = agent_name
        self.model_name = model_name
        self.prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        self.response_hash: Optional[str] = None
        self.latency_ms = 0.0
        self.success = False
        self.error_msg: Optional[str] = None
        self.tier = tier
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.failure_mode: str = ""
        self._start_time: Optional[float] = None

    def start(self) -> None:
        self._start_time = time.perf_counter()

    def set_response(self, response_text: str) -> None:
        self.response_hash = hashlib.sha256(response_text.encode()).hexdigest()[:16]

    def set_tokens(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens

    def set_failure_mode(self, failure_mode: str) -> None:
        self.failure_mode = failure_mode

    def succeed(self) -> None:
        self.success = True
        if self._start_time is not None:
            self.latency_ms = (time.perf_counter() - self._start_time) * 1000

    def fail(self, error: str) -> None:
        self.success = False
        self.error_msg = error
        if self._start_time is not None:
            self.latency_ms = (time.perf_counter() - self._start_time) * 1000

    def persist(self) -> None:
        # Emit LLM latency metric to App Insights
        track_metric(
            "LLM_Call_Latency_ms",
            self.latency_ms,
            {"agent": self.agent_name, "model": self.model_name, "success": str(self.success)},
        )
        cost = estimate_cost(self.model_name, self.prompt_tokens, self.completion_tokens)
        try:
            con = _get_duckdb(self.db_path)
            con.execute(
                """
                INSERT INTO llm_audit
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
                """,
                [
                    self.call_id,
                    self.agent_name,
                    self.model_name,
                    self.prompt_hash,
                    self.response_hash,
                    self.latency_ms,
                    self.success,
                    self.error_msg,
                    self.tier,
                    self.prompt_tokens,
                    self.completion_tokens,
                    cost,
                    self.failure_mode,
                ],
            )
        except Exception as exc:
            logger.warning("audit_persist_failed", error=str(exc))
