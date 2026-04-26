"""Tests for RegistryWriterAgent — insert, dedup, status tracking."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
from partition.db.sqlite_manager import FileRegistryRow, get_engine, get_session, init_db
from partition.entry.registry_writer_agent import RegistryWriterAgent
from partition.models.file_metadata import FileMetadata

# ── Helpers ───────────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


def _make_meta(path: str, content: str = "DATA work.x; RUN;", valid: bool = True) -> FileMetadata:
    raw = content.encode("utf-8")
    return FileMetadata(
        file_path=path,
        encoding="utf-8",
        content_hash=hashlib.sha256(raw).hexdigest(),
        file_size_bytes=len(raw),
        line_count=content.count("\n") + 1,
        lark_valid=valid,
    )


@pytest.fixture()
def db_engine(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = get_engine(str(db_path), _allow_any_path=True)
    init_db(engine)
    return engine


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestRegistryWriterAgent:
    def test_insert_single_file(self, db_engine):
        """A single FileMetadata should result in 1 inserted row."""
        fm = _make_meta("/data/test.sas")
        agent = RegistryWriterAgent()
        result = _run(agent.process([fm], db_engine))

        assert result["inserted"] == 1
        assert result["skipped"] == 0

    def test_idempotent_dedup(self, db_engine):
        """Inserting the same file twice should skip the duplicate."""
        fm = _make_meta("/data/test.sas", "PROC PRINT; RUN;")
        agent = RegistryWriterAgent()

        r1 = _run(agent.process([fm], db_engine))
        assert r1["inserted"] == 1

        # Re-process — same content_hash
        r2 = _run(agent.process([fm], db_engine))
        assert r2["inserted"] == 0
        assert r2["skipped"] == 1

    def test_invalid_file_stored_with_errors(self, db_engine):
        """A file with lark_valid=False should still be written to the registry."""
        fm = _make_meta(
            "/data/broken.sas",
            "%MACRO unclosed;\nDATA work.x; SET work.y; RUN;\n",
            valid=False,
        )
        fm.lark_errors = ["Macro imbalance: 1 %MACRO vs 0 %MEND."]

        agent = RegistryWriterAgent()
        result = _run(agent.process([fm], db_engine))

        assert result["inserted"] == 1

        # Verify the stored row
        sess = get_session(db_engine)
        row = sess.query(FileRegistryRow).filter_by(file_id=str(fm.file_id)).first()
        assert row is not None
        assert row.lark_valid is False
        assert "Macro imbalance" in row.lark_errors
        sess.close()

    def test_different_content_different_hashes(self, db_engine):
        """Two files with different content should both be inserted."""
        fm1 = _make_meta("/data/a.sas", "DATA work.a; RUN;")
        fm2 = _make_meta("/data/b.sas", "DATA work.b; RUN;")

        agent = RegistryWriterAgent()
        result = _run(agent.process([fm1, fm2], db_engine))

        assert result["inserted"] == 2
        assert result["skipped"] == 0

    def test_db_state_after_batch(self, db_engine):
        """After writing 3 files, the database should contain exactly 3 rows."""
        files = [_make_meta(f"/data/file_{i}.sas", f"DATA work.f{i}; RUN;") for i in range(3)]
        agent = RegistryWriterAgent()
        _run(agent.process(files, db_engine))

        sess = get_session(db_engine)
        count = sess.query(FileRegistryRow).count()
        assert count == 3
        sess.close()
