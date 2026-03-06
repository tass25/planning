"""FileProcessor — Consolidated L2-A entry agent.

Merges FileAnalysisAgent + CrossFileDependencyResolver + RegistryWriterAgent
into a single pipeline step: scan → resolve cross-file deps → persist to SQLite.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from partition.base_agent import BaseAgent
from partition.models.file_metadata import FileMetadata

from .file_analysis_agent import FileAnalysisAgent
from .cross_file_dep_resolver import CrossFileDependencyResolver
from .registry_writer_agent import RegistryWriterAgent


class FileProcessor(BaseAgent):
    """Consolidated entry agent: scan files, resolve deps, write to registry.

    Replaces the 3-node L2-A sub-pipeline with a single ``process()`` call.
    """

    agent_name = "FileProcessor"

    def __init__(self, trace_id: UUID | None = None) -> None:
        super().__init__(trace_id)
        self._scanner = FileAnalysisAgent(trace_id=self.trace_id)
        self._resolver = CrossFileDependencyResolver(trace_id=self.trace_id)
        self._writer = RegistryWriterAgent(trace_id=self.trace_id)

    async def process(  # type: ignore[override]
        self,
        input_paths: list[str],
        engine,
    ) -> tuple[list[FileMetadata], dict]:
        """Scan files, resolve cross-file deps, write to registry.

        Args:
            input_paths: SAS file/directory paths to process.
            engine: SQLAlchemy engine for persistence.

        Returns:
            (file_metas, cross_file_deps) tuple.
        """
        all_metas: list[FileMetadata] = []
        errors: list[str] = []

        # Step 1: Scan files
        for path_str in input_paths:
            path = Path(path_str)
            try:
                if path.is_dir():
                    metas = await self._scanner.process(path)
                elif path.is_file() and path.suffix.lower() == ".sas":
                    metas = await self._scanner.process(path.parent)
                    metas = [m for m in metas if Path(m.file_path).resolve() == path.resolve()]
                else:
                    errors.append(f"Invalid path (not .sas or directory): {path}")
                    continue
                all_metas.extend(metas)
            except Exception as exc:
                errors.append(f"File scan failed for {path}: {exc}")
                self.logger.error("file_scan_error", path=str(path), error=str(exc))

        if errors:
            self.logger.warning("file_processor_errors", errors=errors)

        # Step 2: Register in SQLite
        write_result = {}
        if all_metas:
            try:
                write_result = await self._writer.process(all_metas, engine)
            except Exception as exc:
                self.logger.error("registry_write_error", error=str(exc))

        # Step 3: Resolve cross-file dependencies
        cross_deps = {}
        if all_metas:
            all_paths = [Path(m.file_path) for m in all_metas]
            project_root = _common_parent(all_paths)
            try:
                cross_deps = await self._resolver.process(all_metas, project_root, engine)
            except Exception as exc:
                self.logger.warning("cross_file_resolve_error", error=str(exc))

        self.logger.info(
            "file_processor_complete",
            n_files=len(all_metas),
            registered=write_result.get("inserted", 0),
            cross_deps=cross_deps.get("total", 0),
        )
        return all_metas, cross_deps


def _common_parent(paths: list[Path]) -> Path:
    """Return the common parent directory of all paths."""
    if not paths:
        return Path(".")
    resolved = [p.resolve() for p in paths]
    common = resolved[0].parent
    for p in resolved[1:]:
        while not str(p).startswith(str(common)):
            common = common.parent
    return common
