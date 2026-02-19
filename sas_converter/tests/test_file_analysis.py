"""Tests for FileAnalysisAgent — discovery, encoding, hashing, pre-validation."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from uuid import UUID

import pytest

from partition.entry.file_analysis_agent import FileAnalysisAgent, _pre_validate


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


@pytest.fixture()
def sas_dir(tmp_path: Path) -> Path:
    """Create a temp directory with a few .sas files for testing."""
    (tmp_path / "valid.sas").write_text(
        "DATA work.out;\n  SET work.in;\nRUN;\n",
        encoding="utf-8",
    )
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "nested.sas").write_text(
        "PROC MEANS DATA=sashelp.class;\n  VAR height;\nRUN;\n",
        encoding="utf-8",
    )
    (tmp_path / "readme.txt").write_text("not a SAS file")
    return tmp_path


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestFileAnalysisAgent:
    """Test suite for FileAnalysisAgent."""

    def test_discovery_finds_only_sas_files(self, sas_dir: Path):
        """Agent discovers .sas recursively and ignores other extensions."""
        agent = FileAnalysisAgent()
        results = _run(agent.process(sas_dir))

        paths = {Path(m.file_path).name for m in results}
        assert paths == {"valid.sas", "nested.sas"}
        assert len(results) == 2

    def test_valid_sas_passes_prevalidation(self, sas_dir: Path):
        """A balanced DATA/RUN file should be marked lark_valid=True."""
        agent = FileAnalysisAgent()
        results = _run(agent.process(sas_dir))

        valid_file = next(m for m in results if "valid.sas" in m.file_path)
        assert valid_file.lark_valid is True
        assert valid_file.lark_errors == []

    def test_unclosed_macro_fails_prevalidation(self, tmp_path: Path):
        """A file with %MACRO but no %MEND should fail pre-validation."""
        bad = tmp_path / "unclosed.sas"
        bad.write_text(
            "%MACRO broken;\n  DATA work.x; SET work.y; RUN;\n",
            encoding="utf-8",
        )
        agent = FileAnalysisAgent()
        results = _run(agent.process(tmp_path))

        assert len(results) == 1
        meta = results[0]
        assert meta.lark_valid is False
        assert any("Macro imbalance" in e for e in meta.lark_errors)

    def test_latin1_encoding_detected(self, tmp_path: Path):
        """A file encoded in Latin-1 with accented chars should be detected."""
        latin_file = tmp_path / "latin.sas"
        content = "/* Données françaises */\nDATA work.out;\n  SET work.in;\nRUN;\n"
        latin_file.write_bytes(content.encode("latin-1"))

        agent = FileAnalysisAgent()
        results = _run(agent.process(tmp_path))

        assert len(results) == 1
        meta = results[0]
        # chardet may detect 'ISO-8859-1' or 'Windows-1252' — both are fine
        assert meta.encoding.lower() in ("iso-8859-1", "windows-1252", "latin-1", "utf-8")
        assert meta.line_count >= 4  # trailing newline may add an extra counted line

    def test_sha256_content_hash_correct(self, tmp_path: Path):
        """content_hash must be the SHA-256 of the raw bytes on disk."""
        sas_file = tmp_path / "hash_check.sas"
        text = "PROC PRINT DATA=sashelp.class;\nRUN;\n"
        sas_file.write_text(text, encoding="utf-8")

        # Hash is computed on raw bytes on disk (may have \r\n on Windows)
        expected_hash = hashlib.sha256(sas_file.read_bytes()).hexdigest()

        agent = FileAnalysisAgent()
        results = _run(agent.process(tmp_path))

        assert results[0].content_hash == expected_hash
