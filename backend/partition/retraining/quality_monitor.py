"""ConversionQualityMonitor — Continuous Learning

Post-batch quality monitor. Computes success_rate, partial_rate,
avg_llm_confidence, failure_mode_dist. Alerts via structlog WARNING.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

import structlog

log = structlog.get_logger(__name__)


class ConversionQualityMonitor:
    """Post-batch quality monitor. Queries last N conversion_results."""

    def __init__(
        self,
        duckdb_conn,
        success_target: float = 0.70,
        confidence_target: float = 0.75,
        single_mode_cap: float = 0.40,
        window_size: int = 100,
    ):
        self.duckdb_conn = duckdb_conn
        self.success_target = success_target
        self.confidence_target = confidence_target
        self.single_mode_cap = single_mode_cap
        self.window_size = window_size

    def evaluate(self, batch_id: str | None = None) -> dict:
        """Compute quality metrics for the last window_size conversions."""
        rows = self.duckdb_conn.execute(f"""
            SELECT status, llm_confidence, failure_mode_flagged
            FROM conversion_results
            ORDER BY rowid DESC
            LIMIT {self.window_size}
            """).fetchall()

        if not rows:
            log.warning("no_conversion_results_found")
            return {}

        n_total = len(rows)
        statuses = [r[0] for r in rows]
        confidences = [r[1] for r in rows if r[1] is not None]
        failure_modes = [r[2] for r in rows if r[2]]

        n_success = statuses.count("SUCCESS")
        n_partial = statuses.count("PARTIAL")
        n_human = statuses.count("HUMAN_REVIEW")

        success_rate = n_success / n_total
        partial_rate = n_partial / n_total
        human_review_rate = n_human / n_total
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        failure_mode_dist = Counter(failure_modes)

        alerts: list[str] = []

        if success_rate < self.success_target:
            msg = f"success_rate {success_rate:.3f} < {self.success_target}"
            log.warning("quality_alert", alert=msg)
            alerts.append(msg)

        if avg_confidence < self.confidence_target:
            msg = f"avg_confidence {avg_confidence:.3f} < {self.confidence_target}"
            log.warning("quality_alert", alert=msg)
            alerts.append(msg)

        if n_partial > 0:
            for mode, count in failure_mode_dist.items():
                ratio = count / n_partial
                if ratio > self.single_mode_cap:
                    msg = (
                        f"failure_mode '{mode}' = {ratio:.1%} of PARTIALs "
                        f"(>{self.single_mode_cap:.0%})"
                    )
                    log.warning("kb_gap_detected", alert=msg, mode=mode)
                    alerts.append(msg)

        metrics = {
            "metric_id": str(uuid4()),
            "batch_id": batch_id or str(uuid4()),
            "n_evaluated": n_total,
            "success_rate": success_rate,
            "partial_rate": partial_rate,
            "human_review_rate": human_review_rate,
            "avg_llm_confidence": avg_confidence,
            "failure_mode_dist": str(dict(failure_mode_dist)),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._write_metrics(metrics)

        log.info(
            "quality_evaluation_complete",
            success_rate=f"{success_rate:.3f}",
            avg_confidence=f"{avg_confidence:.3f}",
            n_alerts=len(alerts),
        )

        return {**metrics, "alerts": alerts}

    def _write_metrics(self, metrics: dict) -> None:
        """Insert metrics into DuckDB quality_metrics table."""
        self.duckdb_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quality_metrics (
                metric_id VARCHAR,
                batch_id VARCHAR,
                n_evaluated INTEGER,
                success_rate DOUBLE,
                partial_rate DOUBLE,
                human_review_rate DOUBLE,
                avg_llm_confidence DOUBLE,
                failure_mode_dist VARCHAR,
                created_at VARCHAR
            )
            """,
        )
        self.duckdb_conn.execute(
            """
            INSERT INTO quality_metrics
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                metrics["metric_id"],
                metrics["batch_id"],
                metrics["n_evaluated"],
                metrics["success_rate"],
                metrics["partial_rate"],
                metrics["human_review_rate"],
                metrics["avg_llm_confidence"],
                metrics["failure_mode_dist"],
                metrics["created_at"],
            ],
        )
