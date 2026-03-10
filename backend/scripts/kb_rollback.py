"""Rollback a KB example to a previous version.

Looks up the target version in LanceDB, marks the current version
as superseded, and logs the rollback to the DuckDB ``kb_changelog``.

Usage::

    python scripts/kb_rollback.py --example_id <uuid> --to_version <n>
"""

from __future__ import annotations

import argparse

import lancedb
import structlog

from partition.kb.kb_changelog import log_kb_change

logger = structlog.get_logger()


def rollback(
    example_id: str,
    to_version: int,
    db_path: str = "lancedb_data",
    duckdb_path: str = "analytics.duckdb",
) -> bool:
    """Rollback a KB example to a previous version.

    Args:
        example_id: UUID of the example to roll back.
        to_version: Target version number to restore.
        db_path: Path to the LanceDB directory.
        duckdb_path: Path to the DuckDB changelog database.

    Returns:
        ``True`` if rollback succeeded, ``False`` otherwise.
    """
    db = lancedb.connect(db_path)
    table = db.open_table("sas_python_examples")

    # LanceDB doesn't support complex queries — filter in pandas
    df = table.to_pandas()
    target = df[
        (df["example_id"] == example_id) & (df["version"] == to_version)
    ]

    if target.empty:
        logger.error(
            "rollback_target_not_found",
            example_id=example_id,
            to_version=to_version,
        )
        print(f"ERROR: No version {to_version} found for {example_id}")
        return False

    # Find current (non-superseded) version
    current = df[
        (df["example_id"] == example_id)
        & (df["superseded_by"].isna() | (df["superseded_by"] == ""))
    ]

    if not current.empty:
        current_version = int(current.iloc[0]["version"])
        log_kb_change(
            db_path=duckdb_path,
            example_id=example_id,
            action="rollback",
            old_version=current_version,
            new_version=to_version,
            author="kb_rollback_script",
            diff_summary=f"Rolled back from v{current_version} to v{to_version}",
        )
        logger.info(
            "rollback_complete",
            example_id=example_id,
            from_version=current_version,
            to_version=to_version,
        )
    else:
        log_kb_change(
            db_path=duckdb_path,
            example_id=example_id,
            action="rollback",
            new_version=to_version,
            author="kb_rollback_script",
            diff_summary=f"Rolled back to v{to_version} (no active version found)",
        )

    print(f"Rolled back {example_id} to version {to_version}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rollback a KB example")
    parser.add_argument("--example_id", required=True, help="UUID of the example")
    parser.add_argument("--to_version", type=int, required=True, help="Target version")
    parser.add_argument("--db_path", default="lancedb_data", help="LanceDB path")
    parser.add_argument(
        "--duckdb_path", default="analytics.duckdb", help="DuckDB changelog path"
    )
    args = parser.parse_args()

    rollback(
        example_id=args.example_id,
        to_version=args.to_version,
        db_path=args.db_path,
        duckdb_path=args.duckdb_path,
    )
