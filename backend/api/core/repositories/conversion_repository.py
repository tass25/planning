"""Conversion repository — all SQLAlchemy queries for conversions and stages.

# Pattern: Repository

This module is the single source of truth for conversion persistence.
Route handlers MUST call methods here instead of writing inline queries.
This decouples business logic from the ORM and makes Azure SQL migration
a one-file change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from api.core.database import ConversionRow, ConversionStageRow

log = structlog.get_logger("codara.repo.conversions")


class ConversionRepository:
    """CRUD operations for ConversionRow and ConversionStageRow."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Conversions ───────────────────────────────────────────────────────────

    def get_by_id(self, conversion_id: str) -> Optional[ConversionRow]:
        return (
            self.db.query(ConversionRow)
            .filter(ConversionRow.id == conversion_id)
            .first()
        )

    def list_by_user(self, user_id: str) -> list[ConversionRow]:
        return (
            self.db.query(ConversionRow)
            .filter(ConversionRow.user_id == user_id)
            .order_by(ConversionRow.created_at.desc())
            .all()
        )

    def list_all(self) -> list[ConversionRow]:
        return (
            self.db.query(ConversionRow)
            .order_by(ConversionRow.created_at.desc())
            .all()
        )

    def create(self, row: ConversionRow) -> ConversionRow:
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_status(
        self,
        conversion_id: str,
        status: str,
        *,
        duration: Optional[float] = None,
        accuracy: Optional[float] = None,
        python_code: Optional[str] = None,
        validation_report: Optional[str] = None,
        merge_report: Optional[str] = None,
    ) -> Optional[ConversionRow]:
        row = self.get_by_id(conversion_id)
        if row is None:
            return None
        row.status = status
        if duration is not None:
            row.duration = duration
        if accuracy is not None:
            row.accuracy = accuracy
        if python_code is not None:
            row.python_code = python_code
        if validation_report is not None:
            row.validation_report = validation_report
        if merge_report is not None:
            row.merge_report = merge_report
        self.db.commit()
        self.db.refresh(row)
        return row

    # ── Stages ────────────────────────────────────────────────────────────────

    def get_stage(
        self, conversion_id: str, stage_name: str
    ) -> Optional[ConversionStageRow]:
        return (
            self.db.query(ConversionStageRow)
            .filter(
                ConversionStageRow.conversion_id == conversion_id,
                ConversionStageRow.stage == stage_name,
            )
            .first()
        )

    def create_stages(self, stages: list[ConversionStageRow]) -> None:
        for s in stages:
            self.db.add(s)
        self.db.commit()

    def update_stage(
        self,
        conversion_id: str,
        stage_name: str,
        status: str,
        *,
        latency: Optional[float] = None,
        retry_count: Optional[int] = None,
        warnings: Optional[str] = None,
        description: Optional[str] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> Optional[ConversionStageRow]:
        row = self.get_stage(conversion_id, stage_name)
        if row is None:
            return None
        row.status = status
        if latency is not None:
            row.latency = latency
        if retry_count is not None:
            row.retry_count = retry_count
        if warnings is not None:
            row.warnings = warnings
        if description is not None:
            row.description = description
        if started_at is not None:
            row.started_at = started_at
        if completed_at is not None:
            row.completed_at = completed_at
        self.db.commit()
        return row
