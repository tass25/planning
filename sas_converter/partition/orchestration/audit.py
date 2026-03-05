"""LLM audit logger -- logs every LLM call to DuckDB + Azure Application Insights.

Dual logging:
    1. DuckDB ``llm_audit`` table — local analytics, calibration, ablation
    2. Azure App Insights — cloud telemetry (optional, enabled via APPINSIGHTS_CONNECTION_STRING)

Usage as a context manager::

    audit = LLMAuditLogger("analytics.duckdb")
    with audit.log_call("BoundaryDetectorAgent", "gpt-4o-mini", prompt) as call:
        result = llm_client.generate(prompt)
        call.set_response(result)

Migration note (Week 9):
    Previously DuckDB-only local logging. Added Azure Application Insights
    for cloud observability. DuckDB remains primary for local analytics.
    App Insights provides:
    - Real-time LLM call monitoring in Azure Portal
    - Latency percentile tracking (P50/P95/P99)
    - Error rate alerting
    - Cost per model deployment tracking
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from contextlib import contextmanager
from typing import Optional

import duckdb
import structlog

logger = structlog.get_logger()

# ── Azure Application Insights (optional) ────────────────────────────────────
_tc = None
_APP_INSIGHTS_CONN = os.getenv("APPINSIGHTS_CONNECTION_STRING")
if _APP_INSIGHTS_CONN:
    try:
        from opencensus.ext.azure import metrics_exporter
        from opencensus.stats import aggregation, measure, stats, view

        _tc_available = True
        logger.info("appinsights_enabled", connection=_APP_INSIGHTS_CONN[:40] + "...")
    except ImportError:
        _tc_available = False
        logger.warning(
            "appinsights_unavailable",
            msg="opencensus-ext-azure not installed — App Insights disabled",
        )
else:
    _tc_available = False


class LLMAuditLogger:
    """Thin wrapper around DuckDB ``llm_audit`` inserts + Azure App Insights telemetry."""

    def __init__(self, db_path: str = "analytics.duckdb"):
        self.db_path = db_path
        self._appinsights_enabled = _tc_available and bool(_APP_INSIGHTS_CONN)

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
            appinsights_enabled=self._appinsights_enabled,
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
        appinsights_enabled: bool = False,
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
        self._appinsights_enabled = appinsights_enabled

    def start(self) -> None:
        self._start_time = time.perf_counter()

    def set_response(self, response_text: str) -> None:
        self.response_hash = hashlib.sha256(
            response_text.encode()
        ).hexdigest()[:16]

    def succeed(self) -> None:
        self.success = True
        self.latency_ms = (time.perf_counter() - self._start_time) * 1000

    def fail(self, error: str) -> None:
        self.success = False
        self.error_msg = error
        self.latency_ms = (time.perf_counter() - self._start_time) * 1000

    def persist(self) -> None:
        # 1. DuckDB (primary — always)
        try:
            con = duckdb.connect(self.db_path)
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
            con.close()
        except Exception as exc:
            logger.warning("audit_persist_failed", error=str(exc))

        # 2. Azure Application Insights (optional — cloud telemetry)
        if self._appinsights_enabled:
            try:
                from opencensus.ext.azure.log_exporter import AzureLogHandler
                import logging

                az_logger = logging.getLogger("llm_audit")
                if not az_logger.handlers:
                    az_logger.addHandler(
                        AzureLogHandler(
                            connection_string=_APP_INSIGHTS_CONN
                        )
                    )
                properties = {
                    "custom_dimensions": {
                        "call_id": self.call_id,
                        "agent_name": self.agent_name,
                        "model_name": self.model_name,
                        "latency_ms": self.latency_ms,
                        "success": self.success,
                        "tier": self.tier or "unknown",
                        "error": self.error_msg or "",
                    }
                }
                az_logger.info(
                    "llm_call_completed",
                    extra=properties,
                )
            except Exception as exc:
                logger.warning("appinsights_send_failed", error=str(exc))
