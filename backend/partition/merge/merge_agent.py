"""MergeAgent — Consolidated L4 agent.

Combines ImportConsolidator + DependencyInjector + ScriptMerger + ReportAgent
into a single ``process()`` call: merge → report.
"""

from __future__ import annotations

from partition.base_agent import BaseAgent
from partition.merge.script_merger import merge_script
from partition.merge.report_agent import ReportAgent


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
        )

        return {
            "merged_script": merged,
            "report": report,
        }
