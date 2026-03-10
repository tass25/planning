"""KB Changelog — DuckDB mutation logger for Knowledge Base versioning.

Every insert, update, or rollback of a KB example is logged to the
``kb_changelog`` table in the analytics DuckDB database.

This provides:
    - Full audit trail for KB mutations
    - Version history per example_id
    - Rollback support (see ``scripts/kb_rollback.py``)
"""

from __future__ import annotations

import uuid
from datetime import datetime

import duckdb
import structlog

logger = structlog.get_logger()

# ── Schema DDL ────────────────────────────────────────────────────────────────

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS kb_changelog (
    change_id       VARCHAR PRIMARY KEY,
    example_id      VARCHAR NOT NULL,
    action          VARCHAR NOT NULL,     -- insert | update | rollback | delete
    old_version     INTEGER,
    new_version     INTEGER NOT NULL,
    author          VARCHAR NOT NULL,
    diff_summary    VARCHAR,
    changed_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _ensure_table(con: duckdb.DuckDBPyConnection) -> None:
    """Create the ``kb_changelog`` table if it does not exist."""
    con.execute(_CREATE_TABLE)


# ── Public API ────────────────────────────────────────────────────────────────

def log_kb_change(
    db_path: str,
    example_id: str,
    action: str,
    new_version: int,
    author: str,
    old_version: int | None = None,
    diff_summary: str | None = None,
) -> str:
    """Log a KB mutation to the changelog table.

    Args:
        db_path: Path to the DuckDB database file.
        example_id: UUID of the KB example.
        action: One of ``insert``, ``update``, ``rollback``, ``delete``.
        new_version: Version number after the change.
        author: Who/what made the change (e.g. ``"generate_kb_pairs"``).
        old_version: Previous version (None for inserts).
        diff_summary: Human-readable description of the change.

    Returns:
        The ``change_id`` (UUID) of the logged entry.
    """
    change_id = str(uuid.uuid4())
    con = duckdb.connect(db_path)
    try:
        _ensure_table(con)
        con.execute(
            """
            INSERT INTO kb_changelog
                (change_id, example_id, action, old_version, new_version,
                 author, diff_summary, changed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                change_id,
                example_id,
                action,
                old_version,
                new_version,
                author,
                diff_summary,
                datetime.utcnow(),
            ],
        )
    finally:
        con.close()

    logger.info(
        "kb_changelog_entry",
        change_id=change_id,
        example_id=example_id,
        action=action,
        version=new_version,
    )
    return change_id


def get_history(db_path: str, example_id: str) -> list[dict]:
    """Retrieve full changelog for a KB example.

    Args:
        db_path: Path to the DuckDB database file.
        example_id: UUID of the KB example.

    Returns:
        List of changelog dicts ordered by ``changed_at`` ascending.
    """
    con = duckdb.connect(db_path)
    try:
        _ensure_table(con)
        rows = con.execute(
            """
            SELECT change_id, example_id, action, old_version, new_version,
                   author, diff_summary, changed_at
            FROM kb_changelog
            WHERE example_id = ?
            ORDER BY changed_at ASC
            """,
            [example_id],
        ).fetchall()
    finally:
        con.close()

    cols = [
        "change_id", "example_id", "action", "old_version",
        "new_version", "author", "diff_summary", "changed_at",
    ]
    return [dict(zip(cols, row)) for row in rows]
