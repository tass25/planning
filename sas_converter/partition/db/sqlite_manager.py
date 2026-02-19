"""SQLAlchemy models and database management for the file registry."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    Text,
    ForeignKey,
    create_engine,
    event,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

Base = declarative_base()


# ── ORM Models ────────────────────────────────────────────────────────────────

class FileRegistryRow(Base):
    """Stores one row per discovered .sas file."""
    __tablename__ = "file_registry"

    file_id = Column(String, primary_key=True)
    file_path = Column(String, nullable=False)
    encoding = Column(String, nullable=False)
    content_hash = Column(String, nullable=False, unique=True)
    file_size_bytes = Column(Integer)
    line_count = Column(Integer)
    lark_valid = Column(Boolean)
    lark_errors = Column(Text, default="")
    status = Column(String, default="PENDING")
    error_log = Column(Text, default="")
    created_at = Column(String, nullable=False)


class CrossFileDependencyRow(Base):
    """Stores one row per cross-file reference found during scanning."""
    __tablename__ = "cross_file_deps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_file_id = Column(String, ForeignKey("file_registry.file_id"), nullable=False)
    ref_type = Column(String, nullable=False)          # INCLUDE | LIBNAME
    raw_reference = Column(String, nullable=False)      # original text matched
    resolved = Column(Boolean, default=False)
    target_file_id = Column(String, ForeignKey("file_registry.file_id"), nullable=True)
    target_path = Column(String, nullable=True)         # resolved absolute path


class DataLineageRow(Base):
    """Stores one row per dataset-level data-flow edge.

    lineage_type values:
        TABLE_READ  — block reads from source_dataset (SET, MERGE, FROM)
        TABLE_WRITE — block writes to target_dataset  (DATA, CREATE TABLE, INSERT INTO)
    """
    __tablename__ = "data_lineage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_file_id = Column(String, ForeignKey("file_registry.file_id"), nullable=False)
    lineage_type = Column(String, nullable=False)       # TABLE_READ | TABLE_WRITE
    source_dataset = Column(String, nullable=True)      # e.g. 'staging.clean'
    target_dataset = Column(String, nullable=True)      # e.g. 'tgt.summary'
    source_columns = Column(Text, nullable=True)        # JSON list: ["unit_price", "qty"]
    target_column = Column(String, nullable=True)       # e.g. 'revenue'
    transform_expr = Column(String, nullable=True)      # e.g. 'SUM(unit_price * quantity)'
    block_line_start = Column(Integer, nullable=True)   # line in source file
    block_line_end = Column(Integer, nullable=True)


# ── Engine / Session helpers ──────────────────────────────────────────────────

def get_engine(db_path: str = "file_registry.db"):
    """Create a SQLAlchemy engine for the given SQLite database.

    Enables WAL journal mode and foreign keys via PRAGMA statements.
    """
    abs_path = str(Path(db_path).resolve())
    engine = create_engine(f"sqlite:///{abs_path}", echo=False)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_db(engine) -> None:
    """Create all tables that don't already exist."""
    Base.metadata.create_all(engine)


def get_session(engine) -> Session:
    """Return a new Session bound to *engine*."""
    return sessionmaker(bind=engine)()
