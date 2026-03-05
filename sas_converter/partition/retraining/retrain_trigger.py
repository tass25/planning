"""Retraining Trigger — Continuous Learning

Monitors 4 conditions that trigger retraining:
  1. KB grew by >= 500 verified examples since last training
  2. ECE on held-out 20% > 0.12
  3. success_rate < 0.70 for two consecutive batches
  4. KB gap detected by ConversionQualityMonitor
"""

from __future__ import annotations

import ast as _ast
from dataclasses import dataclass
from typing import Optional

import structlog

log = structlog.get_logger(__name__)


@dataclass
class RetrainDecision:
    """Result of the retraining trigger evaluation."""

    should_retrain: bool
    trigger_reason: str
    targeted_category: Optional[str] = None


class RetrainTrigger:
    """Evaluates the 4 retraining conditions. Call .evaluate() after each batch."""

    def __init__(
        self,
        duckdb_conn,
        kb_growth_threshold: int = 500,
        ece_threshold: float = 0.12,
        success_threshold: float = 0.70,
        consecutive_failures: int = 2,
    ):
        self.duckdb_conn = duckdb_conn
        self.kb_growth_threshold = kb_growth_threshold
        self.ece_threshold = ece_threshold
        self.success_threshold = success_threshold
        self.consecutive_failures = consecutive_failures

    def evaluate(self) -> RetrainDecision:
        """Check all 4 conditions. Returns a RetrainDecision."""

        # Condition 1: KB growth
        kb_growth = self._check_kb_growth()
        if kb_growth >= self.kb_growth_threshold:
            log.info("retrain_trigger_kb_growth", growth=kb_growth)
            return RetrainDecision(
                should_retrain=True,
                trigger_reason=(
                    f"KB grew by {kb_growth} examples "
                    f"(threshold: {self.kb_growth_threshold})"
                ),
            )

        # Condition 2: ECE too high
        latest_ece = self._get_latest_ece()
        if latest_ece is not None and latest_ece > self.ece_threshold:
            log.info("retrain_trigger_ece", ece=latest_ece)
            return RetrainDecision(
                should_retrain=True,
                trigger_reason=f"ECE = {latest_ece:.4f} (threshold: {self.ece_threshold})",
            )

        # Condition 3: success_rate < threshold for 2 consecutive batches
        low_success_streak = self._check_consecutive_low_success()
        if low_success_streak >= self.consecutive_failures:
            log.info("retrain_trigger_low_success", streak=low_success_streak)
            return RetrainDecision(
                should_retrain=True,
                trigger_reason=(
                    f"success_rate < {self.success_threshold} for "
                    f"{low_success_streak} consecutive batches"
                ),
            )

        # Condition 4: KB gap detected
        gap_mode = self._check_kb_gap()
        if gap_mode:
            log.info("retrain_trigger_kb_gap", mode=gap_mode)
            return RetrainDecision(
                should_retrain=True,
                trigger_reason=(
                    f"KB gap: '{gap_mode}' accounts for >40% of PARTIAL conversions"
                ),
                targeted_category=gap_mode,
            )

        return RetrainDecision(
            should_retrain=False,
            trigger_reason="no trigger condition met",
        )

    def _check_kb_growth(self) -> int:
        """Get KB examples added since last training."""
        try:
            result = self.duckdb_conn.execute(
                """
                SELECT COUNT(*) FROM kb_changelog WHERE action = 'insert'
                """
            ).fetchone()
            return result[0] if result and result[0] else 0
        except Exception:
            return 0

    def _get_latest_ece(self) -> Optional[float]:
        """Get the most recent ECE score."""
        try:
            result = self.duckdb_conn.execute(
                """
                SELECT ece_score FROM calibration_log
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
            return result[0] if result else None
        except Exception:
            return None

    def _check_consecutive_low_success(self) -> int:
        """Count recent consecutive batches with success_rate < threshold."""
        try:
            rows = self.duckdb_conn.execute(
                """
                SELECT success_rate FROM quality_metrics
                ORDER BY created_at DESC LIMIT 5
                """
            ).fetchall()
            streak = 0
            for row in rows:
                if row[0] < self.success_threshold:
                    streak += 1
                else:
                    break
            return streak
        except Exception:
            return 0

    def _check_kb_gap(self) -> Optional[str]:
        """Check the latest quality_metrics for a KB gap."""
        try:
            result = self.duckdb_conn.execute(
                """
                SELECT failure_mode_dist FROM quality_metrics
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
            if not result or not result[0]:
                return None
            dist = _ast.literal_eval(result[0])
            total_partial = sum(dist.values())
            if total_partial == 0:
                return None
            for mode, count in dist.items():
                if count / total_partial > 0.40:
                    return mode
            return None
        except Exception:
            return None
