"""User repository — all SQLAlchemy queries for UserRow.

# Pattern: Repository
"""

from __future__ import annotations

from typing import Optional

import structlog
from sqlalchemy.orm import Session

from api.core.database import UserRow

log = structlog.get_logger("codara.repo.users")


class UserRepository:
    """CRUD operations for UserRow."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: str) -> Optional[UserRow]:
        return self.db.query(UserRow).filter(UserRow.id == user_id).first()

    def get_by_email(self, email: str) -> Optional[UserRow]:
        return self.db.query(UserRow).filter(UserRow.email == email).first()

    def get_by_github_id(self, github_id: str) -> Optional[UserRow]:
        return self.db.query(UserRow).filter(UserRow.github_id == github_id).first()

    def get_by_verification_token(self, token: str) -> Optional[UserRow]:
        return self.db.query(UserRow).filter(UserRow.verification_token == token).first()

    def list_all(self) -> list[UserRow]:
        return self.db.query(UserRow).order_by(UserRow.created_at.desc()).all()

    def create(self, row: UserRow) -> UserRow:
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update(self, row: UserRow) -> UserRow:
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, user_id: str) -> bool:
        row = self.get_by_id(user_id)
        if row is None:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def increment_conversion_count(self, user_id: str) -> None:
        row = self.get_by_id(user_id)
        if row is not None:
            row.conversion_count = (row.conversion_count or 0) + 1
            self.db.commit()
