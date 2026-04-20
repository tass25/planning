"""RegistryWriterAgent (#3) — Persist FileMetadata to the file_registry table."""

from __future__ import annotations

import json

from ..base_agent import BaseAgent
from ..db.sqlite_manager import FileRegistryRow, get_session
from ..models.file_metadata import FileMetadata


class RegistryWriterAgent(BaseAgent):
    """Write scanned FileMetadata records into the SQLite file_registry table.

    Deduplication is based on ``content_hash``: files with the same hash are
    skipped (INSERT OR IGNORE semantics).

    Inputs:
        files  – list of FileMetadata produced by FileAnalysisAgent.
        engine – SQLAlchemy engine.

    Outputs:
        dict with ``inserted`` and ``skipped`` counts.
    """

    @property
    def agent_name(self) -> str:
        return "RegistryWriterAgent"

    async def process(self, files: list[FileMetadata], engine) -> dict:  # type: ignore[override]
        session = get_session(engine)
        inserted = 0
        skipped = 0

        try:
            for fm in files:
                # Dedup by file_id (primary key) — content_hash dedup would break FK
                # references when the same file is re-uploaded with a new UUID.
                existing = session.query(FileRegistryRow).filter_by(file_id=str(fm.file_id)).first()
                if existing is not None:
                    self.logger.debug("skipping_duplicate", file_path=fm.file_path)
                    skipped += 1
                    continue

                row = FileRegistryRow(
                    file_id=str(fm.file_id),
                    file_path=fm.file_path,
                    encoding=fm.encoding,
                    content_hash=fm.content_hash,
                    file_size_bytes=fm.file_size_bytes,
                    line_count=fm.line_count,
                    lark_valid=fm.lark_valid,
                    lark_errors=json.dumps(fm.lark_errors),
                    status="PENDING",
                    error_log="",
                    created_at=fm.created_at.isoformat(),
                )
                session.add(row)
                inserted += 1

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        self.logger.info(
            "registry_write_complete",
            inserted=inserted,
            skipped=skipped,
        )
        return {"inserted": inserted, "skipped": skipped}
