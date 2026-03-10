"""DataLineageExtractor — Extract table-level data lineage from SAS code.

Detects dataset reads (SET, MERGE, FROM, JOIN, PROC DATA=) and dataset writes
(DATA output, CREATE TABLE, INSERT INTO, OUTPUT OUT=) and stores edges in the
``data_lineage`` SQLite table.

Phase 1 (Week 1–2): table-level lineage via regex.
Phase 2 (Week 3–4): column-level lineage via Lark grammar (deferred).
"""

from __future__ import annotations

import re
from pathlib import Path

from ..base_agent import BaseAgent
from ..models.file_metadata import FileMetadata
from ..db.sqlite_manager import get_session, DataLineageRow


# ── Regex patterns — Table-level reads ────────────────────────────────────────

SET_PATTERN = re.compile(
    r"\bSET\s+([\w.]+(?:\s*\([^)]*\))?(?:\s+[\w.]+(?:\s*\([^)]*\))?)*)\s*;",
    re.IGNORECASE,
)

MERGE_PATTERN = re.compile(
    r"\bMERGE\s+([\w.]+(?:\s*\([^)]*\))?(?:\s+[\w.]+(?:\s*\([^)]*\))?)*)\s*;",
    re.IGNORECASE,
)

FROM_PATTERN = re.compile(
    r"\bFROM\s+([\w.]+)", re.IGNORECASE,
)

JOIN_PATTERN = re.compile(
    r"\b(?:INNER|LEFT|RIGHT|FULL|CROSS)?\s*JOIN\s+([\w.]+)",
    re.IGNORECASE,
)

# PROC ... DATA=dataset — input dataset for PROC SORT, PROC MEANS, PROC EXPORT, etc.
PROC_DATA_PATTERN = re.compile(
    r"\bPROC\s+\w+\b[^;]*\bDATA\s*=\s*([\w.]+)",
    re.IGNORECASE,
)

# ── Regex patterns — Table-level writes ───────────────────────────────────────

DATA_OUTPUT_PATTERN = re.compile(
    r"^\s*DATA\s+([\w.]+(?:\s+[\w.]+)*)\s*[;(]",
    re.IGNORECASE | re.MULTILINE,
)

CREATE_TABLE_PATTERN = re.compile(
    r"\bCREATE\s+TABLE\s+([\w.]+)", re.IGNORECASE,
)

INSERT_INTO_PATTERN = re.compile(
    r"\bINSERT\s+INTO\s+([\w.]+)", re.IGNORECASE,
)

# OUTPUT OUT=dataset — output dataset in PROC steps (PROC MEANS, PROC FREQ, etc.)
OUTPUT_OUT_PATTERN = re.compile(
    r"\bOUTPUT\s+OUT\s*=\s*([\w.]+)",
    re.IGNORECASE,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

# SAS dataset name = optional libref dot name, e.g. "work.temp" or just "temp"
_DATASET_NAME = re.compile(r"[\w.]+")

# Keywords that should NOT be treated as dataset names
_IGNORE_TOKENS = frozenset({
    "_null_", "_data_", "_last_", "_infile_",
})


def _split_datasets(raw: str) -> list[str]:
    """Extract individual dataset names from a whitespace-separated token string.

    Strips dataset options like ``(WHERE=(...))`` and filters out SAS
    automatic variables like ``_NULL_``.
    """
    # Remove parenthesised options first  e.g. "lib.ds (keep=x)"
    cleaned = re.sub(r"\([^)]*\)", "", raw)
    tokens = _DATASET_NAME.findall(cleaned)
    return [
        t for t in tokens
        if t.lower() not in _IGNORE_TOKENS and not t.startswith("_")
    ]


def _line_of(content: str, pos: int) -> int:
    """Return 1-based line number for a character position in *content*."""
    return content[:pos].count("\n") + 1


class DataLineageExtractor(BaseAgent):
    """Scan SAS content for table-level data lineage and persist to DB.

    Detects:
      - **TABLE_READ**: SET, MERGE, FROM, JOIN, PROC DATA=
      - **TABLE_WRITE**: DATA output, CREATE TABLE, INSERT INTO, OUTPUT OUT=

    Inputs:
        files  – list of FileMetadata (with file_path, file_id, encoding).
        engine – SQLAlchemy engine for write operations.

    Outputs:
        Dict with counts of reads/writes found.
    """

    @property
    def agent_name(self) -> str:
        return "DataLineageExtractor"

    async def process(self, files: list[FileMetadata], engine) -> dict:  # type: ignore[override]
        session = get_session(engine)
        total_reads = 0
        total_writes = 0

        try:
            for fm in files:
                filepath = Path(fm.file_path)
                try:
                    content = filepath.read_bytes().decode(fm.encoding, errors="replace")
                except Exception as exc:
                    self.logger.warning("read_failed", file=str(filepath), error=str(exc))
                    continue

                rows = self._extract_lineage(content, str(fm.file_id))
                for row in rows:
                    session.add(row)
                    if row.lineage_type == "TABLE_READ":
                        total_reads += 1
                    else:
                        total_writes += 1

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        self.logger.info(
            "lineage_extraction_complete",
            total_reads=total_reads,
            total_writes=total_writes,
        )

        return {
            "total_reads": total_reads,
            "total_writes": total_writes,
            "total": total_reads + total_writes,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _extract_lineage(self, content: str, source_file_id: str) -> list[DataLineageRow]:
        """Return DataLineageRow objects for every dataset read/write in *content*."""
        rows: list[DataLineageRow] = []

        # --- TABLE_READ: SET ---
        for m in SET_PATTERN.finditer(content):
            line = _line_of(content, m.start())
            for ds in _split_datasets(m.group(1)):
                rows.append(DataLineageRow(
                    source_file_id=source_file_id,
                    lineage_type="TABLE_READ",
                    source_dataset=ds,
                    target_dataset=None,
                    block_line_start=line,
                    block_line_end=line,
                ))

        # --- TABLE_READ: MERGE ---
        for m in MERGE_PATTERN.finditer(content):
            line = _line_of(content, m.start())
            for ds in _split_datasets(m.group(1)):
                rows.append(DataLineageRow(
                    source_file_id=source_file_id,
                    lineage_type="TABLE_READ",
                    source_dataset=ds,
                    target_dataset=None,
                    block_line_start=line,
                    block_line_end=line,
                ))

        # --- TABLE_READ: FROM  (PROC SQL / SQL views) ---
        for m in FROM_PATTERN.finditer(content):
            ds = m.group(1)
            if ds.lower() in _IGNORE_TOKENS:
                continue
            line = _line_of(content, m.start())
            rows.append(DataLineageRow(
                source_file_id=source_file_id,
                lineage_type="TABLE_READ",
                source_dataset=ds,
                target_dataset=None,
                block_line_start=line,
                block_line_end=line,
            ))

        # --- TABLE_READ: JOIN ---
        for m in JOIN_PATTERN.finditer(content):
            ds = m.group(1)
            if ds.lower() in _IGNORE_TOKENS:
                continue
            line = _line_of(content, m.start())
            rows.append(DataLineageRow(
                source_file_id=source_file_id,
                lineage_type="TABLE_READ",
                source_dataset=ds,
                target_dataset=None,
                block_line_start=line,
                block_line_end=line,
            ))

        # --- TABLE_WRITE: DATA output ---
        for m in DATA_OUTPUT_PATTERN.finditer(content):
            line = _line_of(content, m.start())
            for ds in _split_datasets(m.group(1)):
                rows.append(DataLineageRow(
                    source_file_id=source_file_id,
                    lineage_type="TABLE_WRITE",
                    source_dataset=None,
                    target_dataset=ds,
                    block_line_start=line,
                    block_line_end=line,
                ))

        # --- TABLE_WRITE: CREATE TABLE ---
        for m in CREATE_TABLE_PATTERN.finditer(content):
            ds = m.group(1)
            line = _line_of(content, m.start())
            rows.append(DataLineageRow(
                source_file_id=source_file_id,
                lineage_type="TABLE_WRITE",
                source_dataset=None,
                target_dataset=ds,
                block_line_start=line,
                block_line_end=line,
            ))

        # --- TABLE_WRITE: INSERT INTO ---
        for m in INSERT_INTO_PATTERN.finditer(content):
            ds = m.group(1)
            line = _line_of(content, m.start())
            rows.append(DataLineageRow(
                source_file_id=source_file_id,
                lineage_type="TABLE_WRITE",
                source_dataset=None,
                target_dataset=ds,
                block_line_start=line,
                block_line_end=line,
            ))

        # --- TABLE_READ: PROC ... DATA=dataset ---
        for m in PROC_DATA_PATTERN.finditer(content):
            ds = m.group(1)
            if ds.lower() in _IGNORE_TOKENS:
                continue
            line = _line_of(content, m.start())
            rows.append(DataLineageRow(
                source_file_id=source_file_id,
                lineage_type="TABLE_READ",
                source_dataset=ds,
                target_dataset=None,
                block_line_start=line,
                block_line_end=line,
            ))

        # --- TABLE_WRITE: OUTPUT OUT=dataset ---
        for m in OUTPUT_OUT_PATTERN.finditer(content):
            ds = m.group(1)
            line = _line_of(content, m.start())
            rows.append(DataLineageRow(
                source_file_id=source_file_id,
                lineage_type="TABLE_WRITE",
                source_dataset=None,
                target_dataset=ds,
                block_line_start=line,
                block_line_end=line,
            ))

        return rows
