"""FeedbackIngestionAgent — Continuous Learning

Accepts corrections from CLI or automated cross-verifier rejects.
Cross-verifies corrected pair → if confidence >= threshold, upserts to KB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import structlog

log = structlog.get_logger(__name__)


class FeedbackIngestionAgent:
    """Ingests human or automated corrections and upserts to the KB."""

    def __init__(
        self,
        lancedb_table,
        embed_fn,
        cross_verifier_fn,
        duckdb_conn,
        confidence_threshold: float = 0.85,
    ):
        self.lancedb_table = lancedb_table
        self.embed_fn = embed_fn
        self.cross_verifier_fn = cross_verifier_fn
        self.duckdb_conn = duckdb_conn
        self.confidence_threshold = confidence_threshold

    def ingest(
        self,
        conversion_id: str,
        partition_id: str,
        sas_code: str,
        corrected_python: str,
        source: str = "human_correction",
        partition_type: str = "",
        complexity_tier: str = "MODERATE",
        target_runtime: str = "python",
        failure_mode: str = "",
        category: str = "",
    ) -> dict:
        """Process a single correction. Returns feedback_log dict."""
        feedback_id = str(uuid4())

        verification = self.cross_verifier_fn(sas_code, corrected_python)
        confidence = verification.get("confidence", 0.0)
        accepted = confidence >= self.confidence_threshold

        new_kb_id = None
        rejection_reason = None

        if accepted:
            new_kb_id = str(uuid4())
            combined_text = f"SAS:\n{sas_code}\n\nPython:\n{corrected_python}"
            embedding = self.embed_fn(combined_text)

            kb_example = {
                "example_id": new_kb_id,
                "sas_code": sas_code,
                "python_code": corrected_python,
                "embedding": embedding,
                "partition_type": partition_type,
                "complexity_tier": complexity_tier,
                "target_runtime": target_runtime,
                "verified": True,
                "source": "correction",
                "failure_mode": failure_mode,
                "verification_method": "llm_crosscheck",
                "verification_score": confidence,
                "category": category,
                "version": 1,
                "superseded_by": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self.lancedb_table.add([kb_example])

            log.info(
                "correction_accepted",
                feedback_id=feedback_id,
                conversion_id=conversion_id,
                confidence=confidence,
                new_kb_id=new_kb_id,
            )
        else:
            rejection_reason = f"confidence {confidence:.3f} < {self.confidence_threshold}"
            log.warning(
                "correction_rejected",
                feedback_id=feedback_id,
                conversion_id=conversion_id,
                confidence=confidence,
                reason=rejection_reason,
            )

        feedback_log = {
            "feedback_id": feedback_id,
            "conversion_id": conversion_id,
            "partition_id": partition_id,
            "correction_source": source,
            "original_status": "PARTIAL",
            "new_kb_example_id": new_kb_id or "",
            "verifier_confidence": confidence,
            "accepted": accepted,
            "rejection_reason": rejection_reason or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_feedback_log(feedback_log)

        return feedback_log

    def _write_feedback_log(self, log_entry: dict) -> None:
        """Insert feedback log into DuckDB."""
        self.duckdb_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_log (
                feedback_id VARCHAR,
                conversion_id VARCHAR,
                partition_id VARCHAR,
                correction_source VARCHAR,
                original_status VARCHAR,
                new_kb_example_id VARCHAR,
                verifier_confidence DOUBLE,
                accepted BOOLEAN,
                rejection_reason VARCHAR,
                created_at VARCHAR
            )
            """,
        )
        self.duckdb_conn.execute(
            """
            INSERT INTO feedback_log
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                log_entry["feedback_id"],
                log_entry["conversion_id"],
                log_entry["partition_id"],
                log_entry["correction_source"],
                log_entry["original_status"],
                log_entry["new_kb_example_id"],
                log_entry["verifier_confidence"],
                log_entry["accepted"],
                log_entry["rejection_reason"],
                log_entry["created_at"],
            ],
        )
