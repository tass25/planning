"""SQLAlchemy models for the Codara API (users, conversions, KB, audit, analytics)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, ForeignKey, create_engine, event,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

ApiBase = declarative_base()


# ── Users ─────────────────────────────────────────────────────────────────────

class UserRow(ApiBase):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=True)       # nullable for OAuth users
    role = Column(String, default="user")         # admin | user | viewer
    status = Column(String, default="active")     # active | inactive | suspended
    conversion_count = Column(Integer, default=0)
    default_runtime = Column(String, default="python")
    email_notifications = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)
    verification_token = Column(String, nullable=True)
    github_id = Column(String, nullable=True, unique=True)
    created_at = Column(String, nullable=False)


# ── Conversions ───────────────────────────────────────────────────────────────

class ConversionRow(ApiBase):
    __tablename__ = "conversions"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    file_name = Column(String, nullable=False)
    status = Column(String, default="queued")     # queued | running | completed | partial | failed
    runtime = Column(String, default="python")    # python
    duration = Column(Float, default=0.0)
    accuracy = Column(Float, default=0.0)
    sas_code = Column(Text, nullable=True)
    python_code = Column(Text, nullable=True)
    validation_report = Column(Text, nullable=True)
    merge_report = Column(Text, nullable=True)
    created_at = Column(String, nullable=False)

    stages = relationship("ConversionStageRow", back_populates="conversion", cascade="all, delete-orphan")


class ConversionStageRow(ApiBase):
    __tablename__ = "conversion_stages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversion_id = Column(String, ForeignKey("conversions.id"), nullable=False)
    stage = Column(String, nullable=False)
    status = Column(String, default="pending")
    latency = Column(Float, nullable=True)
    retry_count = Column(Integer, default=0)
    warnings = Column(Text, default="[]")         # JSON array
    description = Column(String, nullable=True)     # e.g. "Analyzing SAS code structure..."
    started_at = Column(String, nullable=True)
    completed_at = Column(String, nullable=True)

    conversion = relationship("ConversionRow", back_populates="stages")


# ── Knowledge Base ────────────────────────────────────────────────────────────

class KBEntryRow(ApiBase):
    __tablename__ = "kb_entries"

    id = Column(String, primary_key=True)
    sas_snippet = Column(Text, nullable=False)
    python_translation = Column(Text, nullable=False)
    category = Column(String, nullable=False)
    confidence = Column(Float, default=0.9)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class KBChangelogRow(ApiBase):
    __tablename__ = "kb_changelog"

    id = Column(String, primary_key=True)
    entry_id = Column(String, ForeignKey("kb_entries.id"), nullable=False)
    action = Column(String, nullable=False)       # add | edit | rollback | delete
    user = Column(String, nullable=False)
    timestamp = Column(String, nullable=False)
    description = Column(String, nullable=False)


# ── Audit Logs ────────────────────────────────────────────────────────────────

class AuditLogRow(ApiBase):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True)
    model = Column(String, nullable=False)
    latency = Column(Float, default=0.0)
    cost = Column(Float, default=0.0)
    prompt_hash = Column(String, nullable=False)
    success = Column(Boolean, default=True)
    timestamp = Column(String, nullable=False)


# ── Corrections ───────────────────────────────────────────────────────────────

class CorrectionRow(ApiBase):
    __tablename__ = "corrections"

    id = Column(String, primary_key=True)
    conversion_id = Column(String, ForeignKey("conversions.id"), nullable=False)
    corrected_code = Column(Text, nullable=False)
    explanation = Column(Text, nullable=False)
    category = Column(String, nullable=False)
    submitted_at = Column(String, nullable=False)


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationRow(ApiBase):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String, default="info")         # info | success | warning | error
    read = Column(Boolean, default=False)
    created_at = Column(String, nullable=False)


# ── Engine helpers ────────────────────────────────────────────────────────────

def get_api_engine(db_path: str = "codara_api.db"):
    from pathlib import Path
    abs_path = str(Path(db_path).resolve())
    engine = create_engine(f"sqlite:///{abs_path}", echo=False)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_api_db(engine) -> None:
    ApiBase.metadata.create_all(engine)


def get_api_session(engine) -> Session:
    return sessionmaker(bind=engine)()
