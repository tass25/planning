"""FileAnalysisAgent (#1) — Discover, scan, and pre-validate SAS files."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from uuid import UUID

import chardet

from ..base_agent import BaseAgent
from ..models.file_metadata import FileMetadata


# ── Minimal pre-validation ────────────────────────────────────────────────────
# Instead of a full Lark grammar (Week 3–4), we do a lightweight regex-based
# check that DATA/RUN, PROC/RUN|QUIT, and %MACRO/%MEND blocks are balanced.

_DATA_OPEN = re.compile(r"(?i)\bDATA\b\s+(?!_NULL_\s*;)[^;]+;")
_PROC_OPEN = re.compile(r"(?i)\bPROC\b\s+\w+")
_RUN_CLOSE = re.compile(r"(?i)\bRUN\s*;")
_QUIT_CLOSE = re.compile(r"(?i)\bQUIT\s*;")
_MACRO_OPEN = re.compile(r"(?i)%MACRO\b")
_MACRO_CLOSE = re.compile(r"(?i)%MEND\b")


def _strip_comments(text: str) -> str:
    """Remove SAS block comments and line comments before validation."""
    # Block comments: /* ... */
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # Line comments: * ... ;
    text = re.sub(r"(?m)^\s*\*[^;]*;", "", text)
    return text


def _pre_validate(content: str) -> tuple[bool, list[str]]:
    """Check that SAS blocks are structurally balanced.

    Returns (is_valid, list_of_error_messages).
    """
    cleaned = _strip_comments(content)
    errors: list[str] = []

    # Check DATA … RUN balance
    data_opens = len(_DATA_OPEN.findall(cleaned))
    run_closes = len(_RUN_CLOSE.findall(cleaned))
    quit_closes = len(_QUIT_CLOSE.findall(cleaned))
    proc_opens = len(_PROC_OPEN.findall(cleaned))

    # RUN; can close both DATA steps and PROCs, QUIT; can also close PROCs.
    # We check that openers ≤ closers as a heuristic.
    total_closers = run_closes + quit_closes
    total_openers = data_opens + proc_opens

    if total_openers > total_closers:
        errors.append(
            f"Block imbalance: {total_openers} openers (DATA/PROC) "
            f"but only {total_closers} closers (RUN/QUIT)."
        )

    # Check %MACRO … %MEND balance
    macro_opens = len(_MACRO_OPEN.findall(cleaned))
    macro_closes = len(_MACRO_CLOSE.findall(cleaned))
    if macro_opens != macro_closes:
        errors.append(
            f"Macro imbalance: {macro_opens} %MACRO vs {macro_closes} %MEND."
        )

    return (len(errors) == 0, errors)


class FileAnalysisAgent(BaseAgent):
    """Scan a project directory for .sas files and produce FileMetadata objects.

    Inputs:
        project_root – directory to scan recursively for ``*.sas``.

    Outputs:
        list[FileMetadata] – one entry per discovered file.
    """

    @property
    def agent_name(self) -> str:
        return "FileAnalysisAgent"

    async def process(self, project_root: Path) -> list[FileMetadata]:  # type: ignore[override]
        project_root = Path(project_root)
        sas_files = sorted(project_root.rglob("*.sas"))

        self.logger.info("discovery_start", project_root=str(project_root), file_count=len(sas_files))

        results: list[FileMetadata] = []
        for filepath in sas_files:
            meta = self._analyse_file(filepath)
            results.append(meta)

            log_fn = self.logger.info if meta.lark_valid else self.logger.error
            log_fn(
                "file_scanned",
                file_path=meta.file_path,
                encoding=meta.encoding,
                line_count=meta.line_count,
                lark_valid=meta.lark_valid,
            )

        self.logger.info(
            "discovery_complete",
            total=len(results),
            valid=sum(1 for m in results if m.lark_valid),
            invalid=sum(1 for m in results if not m.lark_valid),
        )
        return results

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _analyse_file(filepath: Path) -> FileMetadata:
        raw_bytes = filepath.read_bytes()

        # Encoding detection
        detected = chardet.detect(raw_bytes)
        encoding = detected.get("encoding") or "utf-8"

        # Decode
        content = raw_bytes.decode(encoding, errors="replace")

        # SHA-256 on raw bytes (encoding-independent dedup)
        content_hash = hashlib.sha256(raw_bytes).hexdigest()

        # Line count
        line_count = content.count("\n") + 1

        # Pre-validation
        lark_valid, lark_errors = _pre_validate(content)

        return FileMetadata(
            file_path=str(filepath),
            encoding=encoding,
            content_hash=content_hash,
            file_size_bytes=len(raw_bytes),
            line_count=line_count,
            lark_valid=lark_valid,
            lark_errors=lark_errors,
        )
