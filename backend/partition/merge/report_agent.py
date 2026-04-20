"""ReportAgent (#14) — Merge Layer (L4)

Generates structured Markdown + HTML conversion reports.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import structlog

log = structlog.get_logger(__name__)


class ReportAgent:
    """Agent #14: Conversion report generation.

    Produces Markdown and HTML reports summarising the conversion outcome
    for a single source file.
    """

    def generate_report(
        self,
        source_file_id: str,
        source_path: str,
        merged_script: dict,
        conversion_results: list[dict],
        validation_results: dict | None = None,
        codebleu_scores: dict | None = None,
        dep_graph_stats: dict | None = None,
        kb_retrieval_stats: dict | None = None,
        output_dir: str = "output",
    ) -> dict:
        """Generate Markdown + HTML report for a converted file."""
        validation_results = validation_results or {}
        codebleu_scores = codebleu_scores or {}
        dep_graph_stats = dep_graph_stats or {}
        kb_retrieval_stats = kb_retrieval_stats or {}

        md_lines = self._build_markdown(
            source_path,
            merged_script,
            conversion_results,
            validation_results,
            codebleu_scores,
            dep_graph_stats,
            kb_retrieval_stats,
        )
        md_text = "\n".join(md_lines)

        # Write Markdown
        stem = Path(source_path).stem
        md_path = Path(output_dir) / f"{stem}_report.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_text, encoding="utf-8")

        # Write HTML
        html_path = Path(output_dir) / f"{stem}_report.html"
        html_text = self._md_to_html(md_text)
        html_path.write_text(html_text, encoding="utf-8")

        report = {
            "report_id": str(uuid4()),
            "source_file_id": source_file_id,
            "total_blocks": merged_script.get("block_count", 0),
            "success_count": sum(1 for cr in conversion_results if cr.get("status") == "SUCCESS"),
            "partial_count": merged_script.get("partial_count", 0),
            "human_review_count": merged_script.get("human_review_count", 0),
            "report_md_path": str(md_path),
            "report_html_path": str(html_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        log.info("report_generated", source=source_path, md=str(md_path))
        return report

    def _build_markdown(
        self,
        source_path: str,
        merged_script: dict,
        conversion_results: list[dict],
        validation_results: dict,
        codebleu_scores: dict,
        dep_graph_stats: dict,
        kb_retrieval_stats: dict,
    ) -> list[str]:
        """Build Markdown report lines."""
        n_total = merged_script.get("block_count", 0)
        n_success = sum(1 for cr in conversion_results if cr.get("status") == "SUCCESS")
        n_partial = merged_script.get("partial_count", 0)
        n_hr = merged_script.get("human_review_count", 0)
        n_failed = n_total - n_success - n_partial - n_hr

        failure_modes = Counter(
            cr.get("failure_mode_flagged", "")
            for cr in conversion_results
            if cr.get("failure_mode_flagged")
        )
        hr_blocks = [cr for cr in conversion_results if cr.get("status") == "HUMAN_REVIEW"]

        lines = [
            f"# Conversion Report: {source_path}",
            "",
            f"**Generated**: {datetime.now(timezone.utc).isoformat()}",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|------:|",
            f"| Total blocks | {n_total} |",
            f"| SUCCESS | {n_success} |",
            f"| PARTIAL | {n_partial} |",
            f"| HUMAN_REVIEW | {n_hr} |",
            f"| FAILED | {n_failed} |",
            f"| Syntax valid | {merged_script.get('syntax_valid', '?')} |",
            "",
        ]

        if failure_modes:
            lines += [
                "## Failure Mode Breakdown",
                "",
                "| Mode | Count |",
                "|------|------:|",
            ]
            for mode, count in failure_modes.most_common():
                lines.append(f"| {mode} | {count} |")
            lines.append("")

        if hr_blocks:
            lines += ["## HUMAN_REVIEW Blocks", ""]
            for i, cr in enumerate(hr_blocks[:10], 1):
                pid = cr.get("block_id", cr.get("partition_id", "?"))
                ptype = cr.get("partition_type", "?")
                lines.append(f"### {i}. Block `{pid}` ({ptype})")
                lines.append("")

        if codebleu_scores:
            lines += [
                "## CodeBLEU Scores",
                "",
                f"- **Overall**: {codebleu_scores.get('overall', '—')}",
                "",
            ]

        if validation_results:
            lines += [
                "## Validation Results",
                "",
                f"- **Pass**: {validation_results.get('pass', 0)}",
                f"- **Fail**: {validation_results.get('fail', 0)}",
                "",
            ]

        if dep_graph_stats:
            lines += [
                "## Dependency Graph Summary",
                "",
                f"- **Nodes**: {dep_graph_stats.get('nodes', 0)}",
                f"- **Edges**: {dep_graph_stats.get('edges', 0)}",
                f"- **SCC groups**: {dep_graph_stats.get('scc_count', 0)}",
                "",
            ]

        if kb_retrieval_stats:
            lines += [
                "## KB Retrieval Stats",
                "",
                f"- **Mean similarity**: {kb_retrieval_stats.get('mean_sim', '—')}",
                f"- **Hit coverage**: {kb_retrieval_stats.get('coverage_pct', '—')}%",
                "",
            ]

        lines += [
            "## Merge Info",
            "",
            f"- **Syntax valid**: {merged_script.get('syntax_valid', '?')}",
            f"- **Output path**: `{merged_script.get('output_path', '?')}`",
        ]
        if merged_script.get("syntax_errors"):
            lines.append("- **Syntax errors**:")
            for err in merged_script["syntax_errors"]:
                lines.append(f"  - {err}")
        lines.append("")

        return lines

    @staticmethod
    def _md_to_html(md_text: str) -> str:
        """Convert Markdown to HTML. Uses markdown2 if available, else basic."""
        try:
            import markdown2

            return markdown2.markdown(md_text, extras=["tables", "fenced-code-blocks"])
        except ImportError:
            # Basic fallback
            html = md_text.replace("\n", "<br>\n")
            return f"<html><body>{html}</body></html>"
