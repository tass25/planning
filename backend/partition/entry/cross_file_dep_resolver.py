"""CrossFileDependencyResolver (#2) — Resolve %INCLUDE and LIBNAME references."""

from __future__ import annotations

import re
from pathlib import Path

from ..base_agent import BaseAgent
from ..db.sqlite_manager import CrossFileDependencyRow, get_session
from ..models.file_metadata import FileMetadata

# ── Regex patterns ────────────────────────────────────────────────────────────

INCLUDE_PATTERN = re.compile(r"""%INCLUDE\s+['"]([^'"]+)['"]""", re.IGNORECASE)

LIBNAME_PATTERN = re.compile(r"""LIBNAME\s+(\w+)\s+['"]([^'"]+)['"]""", re.IGNORECASE)

MACRO_VAR_INCLUDE = re.compile(r"%INCLUDE\s+&(\w+)", re.IGNORECASE)


class CrossFileDependencyResolver(BaseAgent):
    """Scan decoded SAS content for cross-file references and persist them.

    Inputs:
        files        – list of FileMetadata (with file_path and file_id).
        project_root – base directory used for relative path resolution.
        engine       – SQLAlchemy engine for write operations.

    Outputs:
        Writes resolved/unresolved rows to the ``cross_file_deps`` table.
    """

    @property
    def agent_name(self) -> str:
        return "CrossFileDependencyResolver"

    async def process(self, files: list[FileMetadata], project_root: Path, engine) -> dict:  # type: ignore[override]
        project_root = Path(project_root)

        # Build a lookup: normalised_path → file_id
        file_index: dict[str, str] = {}
        for fm in files:
            norm = str(Path(fm.file_path).resolve())
            file_index[norm] = str(fm.file_id)

        session = get_session(engine)
        total = 0
        resolved_count = 0
        unresolved_count = 0

        try:
            for fm in files:
                filepath = Path(fm.file_path)
                try:
                    content = filepath.read_bytes().decode(fm.encoding, errors="replace")
                except Exception as exc:
                    self.logger.warning("read_failed", file=str(filepath), error=str(exc))
                    continue

                deps = self._extract_dependencies(
                    content, filepath, project_root, file_index, str(fm.file_id)
                )
                for dep in deps:
                    session.add(dep)
                    total += 1
                    if dep.resolved:
                        resolved_count += 1
                    else:
                        unresolved_count += 1

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        self.logger.info(
            "dependency_scan_complete",
            total_deps_found=total,
            resolved=resolved_count,
            unresolved=unresolved_count,
        )

        return {
            "total": total,
            "resolved": resolved_count,
            "unresolved": unresolved_count,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _extract_dependencies(
        self,
        content: str,
        source_path: Path,
        project_root: Path,
        file_index: dict[str, str],
        source_file_id: str,
    ) -> list[CrossFileDependencyRow]:
        rows: list[CrossFileDependencyRow] = []

        # %INCLUDE 'path';
        for match in INCLUDE_PATTERN.finditer(content):
            ref_path = match.group(1)
            resolved, target_id, abs_path = self._resolve(
                ref_path, source_path, project_root, file_index
            )
            rows.append(
                CrossFileDependencyRow(
                    source_file_id=source_file_id,
                    ref_type="INCLUDE",
                    raw_reference=ref_path,
                    resolved=resolved,
                    target_file_id=target_id,
                    target_path=abs_path,
                )
            )

        # LIBNAME name 'path';
        for match in LIBNAME_PATTERN.finditer(content):
            lib_name = match.group(1)
            lib_path = match.group(2)
            rows.append(
                CrossFileDependencyRow(
                    source_file_id=source_file_id,
                    ref_type="LIBNAME",
                    raw_reference=f"{lib_name}={lib_path}",
                    resolved=False,  # LIBNAME points to a directory, not a file
                    target_file_id=None,
                    target_path=lib_path,
                )
            )

        # %INCLUDE &macro_var — unresolvable statically
        for match in MACRO_VAR_INCLUDE.finditer(content):
            var_name = match.group(1)
            rows.append(
                CrossFileDependencyRow(
                    source_file_id=source_file_id,
                    ref_type="INCLUDE",
                    raw_reference=f"&{var_name}",
                    resolved=False,
                    target_file_id=None,
                    target_path=None,
                )
            )

        return rows

    @staticmethod
    def _resolve(
        ref_path: str,
        source_path: Path,
        project_root: Path,
        file_index: dict[str, str],
    ) -> tuple[bool, str | None, str | None]:
        """Try to resolve a referenced path against the file index.

        Attempts:
          1. Relative to the source file's directory.
          2. Relative to the project root.

        Returns (resolved, target_file_id, absolute_path).
        """
        candidates = [
            (source_path.parent / ref_path).resolve(),
            (project_root / ref_path).resolve(),
        ]
        for candidate in candidates:
            if not candidate.is_relative_to(project_root):
                continue  # path traversal — skip
            norm = str(candidate)
            if norm in file_index:
                return True, file_index[norm], norm

        return False, None, None
