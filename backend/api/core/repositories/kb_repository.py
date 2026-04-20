"""Knowledge Base repository — all SQLAlchemy queries for KB entries and changelog.

# Pattern: Repository
"""

from __future__ import annotations

from typing import Optional

import structlog
from sqlalchemy.orm import Session

from api.core.database import KBChangelogRow, KBEntryRow

log = structlog.get_logger("codara.repo.kb")


class KBRepository:
    """CRUD operations for KBEntryRow and KBChangelogRow."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Entries ───────────────────────────────────────────────────────────────

    def get_by_id(self, entry_id: str) -> Optional[KBEntryRow]:
        return self.db.query(KBEntryRow).filter(KBEntryRow.id == entry_id).first()

    def list_all(self) -> list[KBEntryRow]:
        return self.db.query(KBEntryRow).order_by(KBEntryRow.updated_at.desc()).all()

    def create(self, row: KBEntryRow) -> KBEntryRow:
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update(self, row: KBEntryRow) -> KBEntryRow:
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, entry_id: str) -> bool:
        row = self.get_by_id(entry_id)
        if row is None:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def count(self) -> int:
        return self.db.query(KBEntryRow).count()

    # ── Changelog ─────────────────────────────────────────────────────────────

    def list_changelog(self) -> list[KBChangelogRow]:
        return self.db.query(KBChangelogRow).order_by(KBChangelogRow.timestamp.desc()).all()

    def add_changelog_entry(self, row: KBChangelogRow) -> KBChangelogRow:
        self.db.add(row)
        self.db.commit()
        return row
