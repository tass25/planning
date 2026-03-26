"""LLM audit logger -- logs every LLM call to DuckDB.

All LLM invocations are recorded in the ``llm_audit`` DuckDB table for
local analytics, calibration, and ablation tracking.

Usage as a context manager::

    audit = LLMAuditLogger("analytics.duckdb")
    with audit.log_call("BoundaryDetectorAgent", "gpt-4o-mini", prompt) as call:
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
                    call_id     VARCHAR,
                    agent_name  VARCHAR,
                    model_name  VARCHAR,
                    prompt_hash VARCHAR,
                    response_hash VARCHAR,
                    latency_ms  DOUBLE,
                    success     BOOLEAN,
                    error_msg   VARCHAR,
                    tier        VARCHAR,
                    created_at  TIMESTAMP DEFAULT NOW()
                )
            """)
            _duckdb_connections[db_path] = conn
        except Exception as exc:
            logger.warning("duckdb_init_failed", db_path=db_path, error=str(exc))
            raise
    return _duckdb_connections[db_path]


class LLMAuditLogger:
    """Thin wrapper around DuckDB ``llm_audit`` inserts."""

    def __init__(self, db_path: str = "analytics.duckdb"):
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
        self._start_time: Optional[float] = None

    def start(self) -> None:
        self._start_time = time.perf_counter()

    def set_response(self, response_text: str) -> None:
        self.response_hash = hashlib.sha256(
            response_text.encode()
        ).hexdigest()[:16]

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
        try:
            con = _get_duckdb(self.db_path)
            con.execute(
                """
                INSERT INTO llm_audit
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
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
                ],
            )
        except Exception as exc:
            logger.warning("audit_persist_failed", error=str(exc))
