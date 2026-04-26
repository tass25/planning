"""Tests for CrossFileDependencyResolver — include, LIBNAME, macro-var refs."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from partition.db.sqlite_manager import get_engine, get_session, init_db
from partition.entry.cross_file_dep_resolver import CrossFileDependencyResolver
from partition.models.file_metadata import FileMetadata

# ── Helpers ───────────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


def _make_meta(tmp_path: Path, name: str, content: str) -> FileMetadata:
    """Write a .sas file and return a FileMetadata for it."""
    filepath = tmp_path / name
    filepath.write_text(content, encoding="utf-8")
    import hashlib

    raw = filepath.read_bytes()
    return FileMetadata(
        file_path=str(filepath),
        encoding="utf-8",
        content_hash=hashlib.sha256(raw).hexdigest(),
        file_size_bytes=len(raw),
        line_count=content.count("\n") + 1,
        lark_valid=True,
    )


@pytest.fixture()
def db_engine(tmp_path: Path):
    """Create a temp SQLite DB with tables initialised."""
    db_path = tmp_path / "test.db"
    engine = get_engine(str(db_path))
    init_db(engine)
    return engine


def _insert_registry_row(engine, fm: FileMetadata):
    """Insert a FileRegistryRow so FK constraints are satisfied."""
    from partition.db.sqlite_manager import FileRegistryRow

    sess = get_session(engine)
    sess.add(
        FileRegistryRow(
            file_id=str(fm.file_id),
            file_path=fm.file_path,
            encoding=fm.encoding,
            content_hash=fm.content_hash,
            file_size_bytes=fm.file_size_bytes,
            line_count=fm.line_count,
            lark_valid=fm.lark_valid,
            lark_errors="[]",
            status="PENDING",
            error_log="",
            created_at=fm.created_at.isoformat(),
        )
    )
    sess.commit()
    sess.close()


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestCrossFileDependencyResolver:
    def test_resolved_include(self, tmp_path: Path, db_engine):
        """A %INCLUDE pointing to an existing file should be resolved."""
        target = _make_meta(tmp_path, "macros.sas", "/* macros */\n")
        source = _make_meta(
            tmp_path,
            "main.sas",
            "%INCLUDE 'macros.sas';\nDATA work.x; SET work.y; RUN;\n",
        )
        _insert_registry_row(db_engine, target)
        _insert_registry_row(db_engine, source)

        agent = CrossFileDependencyResolver()
        # Both files must be in the list so the resolver can build a complete file_index
        result = _run(agent.process([source, target], tmp_path, db_engine))

        assert result["resolved"] >= 1

    def test_macro_var_include_unresolved(self, tmp_path: Path, db_engine):
        """%INCLUDE &VAR should be recorded but marked unresolved."""
        src = _make_meta(
            tmp_path,
            "dynamic.sas",
            "%INCLUDE &config_path;\n",
        )
        _insert_registry_row(db_engine, src)

        agent = CrossFileDependencyResolver()
        result = _run(agent.process([src], tmp_path, db_engine))

        assert result["unresolved"] >= 1
        assert result["resolved"] == 0

    def test_libname_detected(self, tmp_path: Path, db_engine):
        """LIBNAME statements should be detected as deps."""
        src = _make_meta(
            tmp_path,
            "setup.sas",
            "LIBNAME mylib '/data/warehouse';\nDATA mylib.out; SET work.in; RUN;\n",
        )
        _insert_registry_row(db_engine, src)

        agent = CrossFileDependencyResolver()
        result = _run(agent.process([src], tmp_path, db_engine))

        assert result["total"] >= 1
        # LIBNAME refs are always unresolved (directory, not file)
        assert result["unresolved"] >= 1

    def test_no_refs_produces_zero(self, tmp_path: Path, db_engine):
        """A file with no cross-file references should produce zero deps."""
        src = _make_meta(
            tmp_path,
            "standalone.sas",
            "DATA work.out;\n  x = 1;\nRUN;\n",
        )
        _insert_registry_row(db_engine, src)

        agent = CrossFileDependencyResolver()
        result = _run(agent.process([src], tmp_path, db_engine))

        assert result["total"] == 0

    def test_resolution_rate(self, tmp_path: Path, db_engine):
        """With 1 resolvable and 1 unresolvable ref, resolution rate = 50%."""
        target = _make_meta(tmp_path, "helpers.sas", "/* helpers */\n")
        src = _make_meta(
            tmp_path,
            "caller.sas",
            "%INCLUDE 'helpers.sas';\n%INCLUDE &dynamic;\n",
        )
        _insert_registry_row(db_engine, target)
        _insert_registry_row(db_engine, src)

        agent = CrossFileDependencyResolver()
        result = _run(agent.process([src, target], tmp_path, db_engine))

        assert result["total"] == 2
        assert result["resolved"] == 1
        assert result["unresolved"] == 1
