"""SQLAlchemy models and database management for the file registry."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

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
    ref_type = Column(String, nullable=False)  # INCLUDE | LIBNAME
    raw_reference = Column(String, nullable=False)  # original text matched
    resolved = Column(Boolean, default=False)
    target_file_id = Column(String, ForeignKey("file_registry.file_id"), nullable=True)
    target_path = Column(String, nullable=True)  # resolved absolute path


class DataLineageRow(Base):
    """Stores one row per dataset-level data-flow edge.

    lineage_type values:
        TABLE_READ  — block reads from source_dataset (SET, MERGE, FROM)
        TABLE_WRITE — block writes to target_dataset  (DATA, CREATE TABLE, INSERT INTO)
    """

    __tablename__ = "data_lineage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_file_id = Column(String, ForeignKey("file_registry.file_id"), nullable=False)
    lineage_type = Column(String, nullable=False)  # TABLE_READ | TABLE_WRITE
    source_dataset = Column(String, nullable=True)  # e.g. 'staging.clean'
    target_dataset = Column(String, nullable=True)  # e.g. 'tgt.summary'
    source_columns = Column(Text, nullable=True)  # JSON list: ["unit_price", "qty"]
    target_column = Column(String, nullable=True)  # e.g. 'revenue'
    transform_expr = Column(String, nullable=True)  # e.g. 'SUM(unit_price * quantity)'
    block_line_start = Column(Integer, nullable=True)  # line in source file
    block_line_end = Column(Integer, nullable=True)


class PartitionIRRow(Base):
    """Stores one row per partitioned SAS code block."""

    __tablename__ = "partition_ir"

    partition_id = Column(String, primary_key=True)
    source_file_id = Column(String, ForeignKey("file_registry.file_id"), nullable=False)
    partition_type = Column(String, nullable=False)
    risk_level = Column(String, default="UNCERTAIN")
    conversion_status = Column(String, default="HUMAN_REVIEW")
    content_hash = Column(String, nullable=False)
    complexity_score = Column(Float, default=0.0)
    calibration_confidence = Column(Float, default=0.0)
    strategy = Column(String, default="FLAT_PARTITION")
    line_start = Column(Integer, nullable=False)
    line_end = Column(Integer, nullable=False)
    control_depth = Column(Integer, default=0)
    has_macros = Column(Boolean, default=False)
    has_nested_sql = Column(Boolean, default=False)
    raw_code = Column(Text, default="")
    raptor_leaf_id = Column(String, nullable=True)
    raptor_cluster_id = Column(String, nullable=True)
    raptor_root_id = Column(String, nullable=True)
    scc_id = Column(String, nullable=True)
    created_at = Column(String, nullable=False)


class ConversionResultRow(Base):
    """Stores one row per completed block conversion."""

    __tablename__ = "conversion_results"

    conversion_id = Column(String, primary_key=True)
    partition_id = Column(String, ForeignKey("partition_ir.partition_id"), nullable=False)
    target_lang = Column(String, default="python")
    translated_code = Column(Text, default="")
    validation_status = Column(String, default="PENDING")
    error_log = Column(Text, default="")
    llm_model = Column(String, nullable=True)
    llm_tier = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(String, nullable=False)


class MergedScriptRow(Base):
    """Stores one row per merged output script."""

    __tablename__ = "merged_scripts"

    script_id = Column(String, primary_key=True)
    source_file_id = Column(String, ForeignKey("file_registry.file_id"), nullable=False)
    output_path = Column(String, nullable=False)
    n_blocks = Column(Integer, default=0)
    status = Column(String, default="PENDING")
    created_at = Column(String, nullable=False)


# ── Engine / Session helpers ──────────────────────────────────────────────────


def get_engine(db_path: str = "data/file_registry.db"):
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


# Current schema version — bump when ORM models change.
SCHEMA_VERSION = 1


def init_db(engine) -> None:
    """Create all tables that don't already exist, then record schema version."""
    Base.metadata.create_all(engine)

    with engine.connect() as conn:
        conn.execute(
            __import__("sqlalchemy").text(
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER NOT NULL, applied_at TEXT NOT NULL)"
            )
        )
        row = conn.execute(
            __import__("sqlalchemy").text("SELECT MAX(version) FROM schema_version")
        ).scalar()
        current = row or 0
        if current < SCHEMA_VERSION:
            conn.execute(
                __import__("sqlalchemy").text(
                    "INSERT INTO schema_version VALUES (:v, datetime('now'))"
                ),
                {"v": SCHEMA_VERSION},
            )
            conn.commit()


def get_session(engine) -> Session:
    """Return a new Session bound to *engine*."""
    return sessionmaker(bind=engine)()
