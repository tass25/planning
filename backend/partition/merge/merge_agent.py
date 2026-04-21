"""MergeAgent — Consolidated L4 agent.

Combines ImportConsolidator + DependencyInjector + ScriptMerger + ReportAgent
into a single ``process()`` call: merge → report.
"""

from __future__ import annotations

from partition.base_agent import BaseAgent
from partition.merge.namespace_checker import check_namespace
from partition.merge.report_agent import ReportAgent
from partition.merge.script_merger import merge_script


class MergeAgent(BaseAgent):
    """Consolidated merge agent: assemble final scripts and generate reports."""

    agent_name = "MergeAgent"

    def __init__(self, **kwargs):
        super().__init__()
        self._reporter = ReportAgent()

    async def process(  # type: ignore[override]
        self,
        conversion_results: list[dict],
        partitions: list[dict],
        source_file_id: str,
        source_path: str,
        target_runtime: str = "python",
        output_dir: str = "output",
        unresolved_refs: list[str] | None = None,
        cross_file_sources: dict[str, str] | None = None,
    ) -> dict:
        """Merge translated partitions into a final script and generate report.

        Returns:
            Dict with merged_script and report metadata.
        """
        merged = merge_script(
            conversion_results=conversion_results,
            partitions=partitions,
            source_file_id=source_file_id,
            source_path=source_path,
            target_runtime=target_runtime,
            output_dir=output_dir,
            unresolved_refs=unresolved_refs,
            cross_file_sources=cross_file_sources,
        )

        # ── Namespace safety check on final merged Python ─────────────────────
        merged_code = merged.get("python_script", "") or ""
        ns_result = check_namespace(merged_code)
        if ns_result.has_errors or ns_result.has_warnings:
            self.logger.warning(
                "namespace_violations",
                source=source_path,
                errors=len(ns_result.errors),
                warnings=len(ns_result.warnings),
            )
            merged["namespace_check"] = {
                "errors": [str(e) for e in ns_result.errors],
                "warnings": [str(w) for w in ns_result.warnings],
                "report": ns_result.to_report_block(),
            }
        else:
            merged["namespace_check"] = {"errors": [], "warnings": [], "report": ""}

        report = self._reporter.generate_report(
            source_file_id=source_file_id,
            source_path=source_path,
            merged_script=merged,
            conversion_results=conversion_results,
            output_dir=output_dir,
        )

        self.logger.info(
            "merge_complete",
            source=source_path,
            status=merged.get("status"),
            blocks=merged.get("block_count"),
            ns_errors=len(ns_result.errors),
            ns_warnings=len(ns_result.warnings),
        )

        return {
            "merged_script": merged,
            "report": report,
        }
