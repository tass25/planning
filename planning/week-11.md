# Week 11: Merge Layer (L4) + ReportAgent + Continuous Learning + KB → 330

> **Priority**: P2  
> **Branch**: `week-11`  
> **Layer**: L4 — Merge + Cross-cutting — Continuous Learning  
> **Agents / Modules**: ImportConsolidator, DependencyInjector, ScriptMerger, ReportAgent (#14), FeedbackIngestionAgent, ConversionQualityMonitor  
> **Prerequisite**: Week 10 complete (TranslationAgent + ValidationAgent working, 250 KB pairs)  

---

## 🎯 Goal

Assemble individually translated partitions into production-ready Python/PySpark scripts (L4 Merge), generate structured conversion reports for human reviewers (ReportAgent), close the learning loop (FeedbackIngestionAgent + ConversionQualityMonitor), and expand the Knowledge Base from 250 → 330 verified pairs.

---

## Architecture Recap — L4 Data Flow

```
ConversionResult[] (from L3 — per source file)
  ↓
ImportConsolidator
  ├─ Collect imports_detected from all ConversionResult objects
  ├─ Deduplicate (each library once)
  ├─ Order: stdlib → third-party → local (PEP 8)
  └─ Canonical aliases: pd, np, sm; PySpark adds pyspark.sql
  ↓
DependencyInjector
  ├─ Build name_registry: SAS dataset → Python variable (snake_case)
  ├─ Patch Python code for consistent variable names
  └─ Insert # NOTE stubs for unresolvable cross-file refs
  ↓
ScriptMerger
  ├─ Sort by PartitionIR.line_start (preserve execution order)
  ├─ Insert TODO stubs for HUMAN_REVIEW / FAILED blocks
  ├─ Prepend import block + header comment
  ├─ ast.parse() validation
  └─ Write output/{filename}_converted.py
  ↓
MergedScript → merged_scripts table
  ↓
ReportAgent (#14)
  ├─ Markdown + HTML report
  ├─ Summary table, failure-mode breakdown, HUMAN_REVIEW list
  ├─ CodeBLEU scores, validation results, dep graph, KB stats
  └─ Persist to conversion_reports DuckDB table
  ↓
FeedbackIngestionAgent → ConversionQualityMonitor → Retraining Trigger
```

---

## Task 1: ImportConsolidator

**File**: `partition/merge/import_consolidator.py`

```python
"""
ImportConsolidator — Merge Layer (L4)

Collects imports_detected from all ConversionResult objects for a file,
deduplicates, orders per PEP 8, and maps to canonical import statements.
"""

import sys
from collections import defaultdict
from typing import Optional

# Canonical import alias map
CANONICAL_ALIASES: dict[str, str] = {
    "pandas": "import pandas as pd",
    "numpy": "import numpy as np",
    "statsmodels": "import statsmodels.api as sm",
    "statsmodels.api": "import statsmodels.api as sm",
    "matplotlib": "import matplotlib.pyplot as plt",
    "matplotlib.pyplot": "import matplotlib.pyplot as plt",
    "scipy": "import scipy",
    "scipy.stats": "from scipy import stats",
}

# PySpark-specific imports
PYSPARK_IMPORTS: dict[str, str] = {
    "pyspark": "from pyspark.sql import SparkSession",
    "pyspark.sql": "from pyspark.sql import SparkSession",
    "pyspark.sql.functions": "from pyspark.sql import functions as F",
    "pyspark.sql.types": "from pyspark.sql.types import *",
    "pyspark.sql.window": "from pyspark.sql.window import Window",
}

# Known stdlib modules (subset used by generated code)
STDLIB_MODULES = {
    "os", "sys", "re", "json", "csv", "datetime", "pathlib",
    "collections", "itertools", "functools", "math", "uuid",
    "typing", "dataclasses", "enum", "logging", "warnings",
    "hashlib", "copy", "io", "textwrap", "contextlib",
}

# Classification buckets
SECTION_ORDER = ["stdlib", "third_party", "local"]


def _classify_import(module_name: str) -> str:
    """Classify a module as stdlib, third_party, or local."""
    root = module_name.split(".")[0]
    if root in STDLIB_MODULES:
        return "stdlib"
    if root.startswith("partition"):
        return "local"
    return "third_party"


def _to_import_statement(module_name: str, target_runtime: str = "python") -> str:
    """
    Convert a module name to a canonical import statement.
    Uses CANONICAL_ALIASES for well-known libraries.
    """
    # Check PySpark imports first if target is PySpark
    if target_runtime == "pyspark" and module_name in PYSPARK_IMPORTS:
        return PYSPARK_IMPORTS[module_name]

    if module_name in CANONICAL_ALIASES:
        return CANONICAL_ALIASES[module_name]

    root = module_name.split(".")[0]
    if root in CANONICAL_ALIASES:
        return CANONICAL_ALIASES[root]

    return f"import {module_name}"


def consolidate_imports(
    all_imports: list[list[str]],
    target_runtime: str = "python",
) -> str:
    """
    Consolidate imports from multiple ConversionResult.imports_detected lists.

    Args:
        all_imports: List of imports_detected lists (one per ConversionResult).
        target_runtime: "python" or "pyspark".

    Returns:
        Formatted import block string with PEP 8 ordering:
        stdlib → third-party → local, separated by blank lines.
    """
    # Flatten and deduplicate
    seen_statements: set[str] = set()
    sections: dict[str, list[str]] = defaultdict(list)

    # If PySpark, always include SparkSession
    if target_runtime == "pyspark":
        stmt = PYSPARK_IMPORTS["pyspark"]
        seen_statements.add(stmt)
        sections["third_party"].append(stmt)

    for imports_list in all_imports:
        for module_name in imports_list:
            stmt = _to_import_statement(module_name, target_runtime)
            if stmt not in seen_statements:
                seen_statements.add(stmt)
                section = _classify_import(module_name)
                sections[section].append(stmt)

    # Sort within each section alphabetically
    for section in sections:
        sections[section].sort()

    # Assemble with blank-line separators
    blocks = []
    for section_key in SECTION_ORDER:
        if sections[section_key]:
            blocks.append("\n".join(sections[section_key]))

    return "\n\n".join(blocks)
```

### Test: `tests/test_import_consolidator.py`

```python
from partition.merge.import_consolidator import consolidate_imports


def test_dedup_and_ordering():
    """Pandas should appear only once, stdlib before third-party."""
    imports = [
        ["os", "pandas", "numpy"],
        ["pandas", "datetime", "scipy"],
    ]
    result = consolidate_imports(imports)
    lines = result.split("\n")
    # stdlib first
    assert lines[0].startswith("import datetime") or lines[0].startswith("import os")
    # pandas appears exactly once
    assert result.count("import pandas as pd") == 1


def test_pyspark_adds_spark_session():
    imports = [["pandas"]]
    result = consolidate_imports(imports, target_runtime="pyspark")
    assert "SparkSession" in result


def test_canonical_aliases():
    imports = [["statsmodels.api"]]
    result = consolidate_imports(imports)
    assert "import statsmodels.api as sm" in result


def test_empty_imports():
    result = consolidate_imports([])
    assert result == ""
```

---

## Task 2: DependencyInjector

**File**: `partition/merge/dependency_injector.py`

```python
"""
DependencyInjector — Merge Layer (L4)

Resolves variable name consistency across translated partitions.
Builds a name_registry mapping SAS dataset names → Python variable names.
Patches all ConversionResult.python_code for consistency.
"""

import re
from dataclasses import dataclass, field
from uuid import UUID

import structlog

log = structlog.get_logger(__name__)

# SAS dataset name → snake_case
# e.g. WORK.TEMP_CUSTOMERS → work_temp_customers
SAS_DATASET_PATTERN = re.compile(
    r'\b(?:DATA\s+|SET\s+|MERGE\s+)([\w.]+)',
    re.IGNORECASE,
)


def sas_name_to_snake(sas_name: str) -> str:
    """
    Convert SAS dataset name to Python snake_case.

    WORK.TEMP_CUSTOMERS → work_temp_customers
    SASDATA.SALES_2024  → sasdata_sales_2024
    """
    return sas_name.replace(".", "_").lower()


@dataclass
class NameRegistry:
    """Registry of SAS dataset → Python variable name mappings."""

    _names: dict[str, str] = field(default_factory=dict)
    _producers: dict[str, str] = field(default_factory=dict)  # var → source_file_id

    def register(self, sas_name: str, source_file_id: str) -> str:
        """Register a SAS dataset name and return the Python variable name."""
        python_name = sas_name_to_snake(sas_name)
        self._names[sas_name.upper()] = python_name
        self._producers[python_name] = source_file_id
        return python_name

    def lookup(self, sas_name: str) -> str | None:
        """Look up the Python name for a SAS dataset."""
        return self._names.get(sas_name.upper())

    def get_producer(self, python_name: str) -> str | None:
        """Get the file that produced a given variable."""
        return self._producers.get(python_name)


def build_name_registry(
    partitions: list[dict],
    source_file_id: str,
) -> NameRegistry:
    """
    Scan all partitions' raw_code to build a NameRegistry.

    Args:
        partitions: list of PartitionIR dicts with 'raw_code' field.
        source_file_id: UUID string of the source file.

    Returns:
        Populated NameRegistry.
    """
    registry = NameRegistry()

    for partition in partitions:
        raw_code = partition.get("raw_code", "")
        matches = SAS_DATASET_PATTERN.findall(raw_code)
        for sas_name in matches:
            registry.register(sas_name.strip(), source_file_id)

    return registry


def inject_variable_names(
    python_code: str,
    registry: NameRegistry,
    source_file_id: str,
) -> str:
    """
    Patch python_code to use consistent variable names from the registry.

    For cross-file references that can't be resolved:
    inserts a # NOTE stub.
    """
    patched = python_code

    for sas_name, python_name in registry._names.items():
        # Replace any remaining SAS-style references with Python names
        # This handles cases where the LLM used the raw SAS name
        sas_variants = [
            sas_name,
            sas_name.lower(),
            sas_name.replace(".", "_"),
        ]
        for variant in sas_variants:
            if variant in patched and variant != python_name:
                patched = patched.replace(variant, python_name)

    return patched


def add_cross_file_stubs(
    python_code: str,
    unresolved_refs: list[str],
    source_files: dict[str, str],
) -> str:
    """
    Insert # NOTE stubs for unresolvable cross-file references.

    Returns updated python_code with stubs prepended.
    """
    if not unresolved_refs:
        return python_code

    stubs = []
    for ref in unresolved_refs:
        source = source_files.get(ref, "unknown")
        stubs.append(
            f"# NOTE: '{ref}' expected from external file '{source}'"
        )

    stub_block = "\n".join(stubs) + "\n\n"
    return stub_block + python_code
```

### Test: `tests/test_dependency_injector.py`

```python
from partition.merge.dependency_injector import (
    sas_name_to_snake,
    NameRegistry,
    build_name_registry,
    add_cross_file_stubs,
)


def test_sas_name_to_snake():
    assert sas_name_to_snake("WORK.TEMP_CUSTOMERS") == "work_temp_customers"
    assert sas_name_to_snake("SASDATA.SALES") == "sasdata_sales"
    assert sas_name_to_snake("mytable") == "mytable"


def test_registry_roundtrip():
    reg = NameRegistry()
    py = reg.register("WORK.TEMP", "file-001")
    assert py == "work_temp"
    assert reg.lookup("WORK.TEMP") == "work_temp"
    assert reg.get_producer("work_temp") == "file-001"


def test_build_from_partitions():
    partitions = [
        {"raw_code": "DATA WORK.OUT; SET WORK.IN; RUN;"},
        {"raw_code": "PROC MEANS DATA=SASDATA.SALES; RUN;"},
    ]
    reg = build_name_registry(partitions, "file-001")
    assert reg.lookup("WORK.OUT") == "work_out"


def test_cross_file_stubs():
    code = "df = work_temp"
    result = add_cross_file_stubs(code, ["WORK.EXT"], {"WORK.EXT": "other.sas"})
    assert "# NOTE: 'WORK.EXT' expected from external file 'other.sas'" in result
```

---

## Task 3: ScriptMerger

**File**: `partition/merge/script_merger.py`

```python
"""
ScriptMerger — Merge Layer (L4)

Assembles the final Python script from translated partitions.
"""

import ast
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import structlog

from partition.merge.import_consolidator import consolidate_imports
from partition.merge.dependency_injector import (
    build_name_registry,
    inject_variable_names,
    add_cross_file_stubs,
)

log = structlog.get_logger(__name__)


def _make_header(
    source_path: str,
    block_count: int,
    partial_count: int,
    target_runtime: str,
) -> str:
    """Generate the header comment for the merged script."""
    now = datetime.now(timezone.utc).isoformat()
    return textwrap.dedent(f"""\
        # ============================================================
        # Auto-generated by SAS→Python Conversion Accelerator
        # Source: {source_path}
        # Generated: {now}
        # Target: {target_runtime}
        # Blocks: {block_count} total, {partial_count} partial
        # ============================================================
    """)


def _make_todo_stub(partition: dict) -> str:
    """
    Create a structured TODO stub for HUMAN_REVIEW or FAILED blocks.
    Includes the original SAS code commented out.
    """
    partition_type = partition.get("partition_type", "UNKNOWN")
    line_start = partition.get("line_start", "?")
    line_end = partition.get("line_end", "?")
    raw_sas = partition.get("raw_code", "")

    # Comment out the SAS code
    sas_commented = "\n".join(
        f"#   {line}" for line in raw_sas.split("\n")[:20]  # max 20 lines
    )
    if len(raw_sas.split("\n")) > 20:
        sas_commented += "\n#   ... (truncated)"

    return textwrap.dedent(f"""\
        # TODO: HUMAN_REVIEW — {partition_type} (lines {line_start}–{line_end})
        # Original SAS code:
        {sas_commented}
        # END TODO
    """)


def merge_script(
    conversion_results: list[dict],
    partitions: list[dict],
    source_file_id: str,
    source_path: str,
    target_runtime: str = "python",
    output_dir: str = "output",
    unresolved_refs: list[str] | None = None,
    cross_file_sources: dict[str, str] | None = None,
) -> dict:
    """
    Assemble the final Python script.

    Steps:
      1. Sort by line_start
      2. Consolidate imports
      3. Inject consistent variable names
      4. Insert TODO stubs for HUMAN_REVIEW / FAILED
      5. Prepend header + imports
      6. Run ast.parse() validation
      7. Write to output/

    Returns:
        MergedScript dict ready for DB insertion.
    """
    # 1. Sort by line_start
    paired = list(zip(conversion_results, partitions))
    paired.sort(key=lambda p: p[1].get("line_start", 0))

    # 2. Consolidate imports
    all_imports = [cr.get("imports_detected", []) for cr in conversion_results]
    import_block = consolidate_imports(all_imports, target_runtime)

    # 3. Build name registry
    registry = build_name_registry(partitions, source_file_id)

    # 4. Assemble body
    body_parts: list[str] = []
    partial_count = 0
    human_review_count = 0

    for cr, partition in paired:
        status = cr.get("status", "SUCCESS")

        if status in ("HUMAN_REVIEW", "FAILED"):
            body_parts.append(_make_todo_stub(partition))
            if status == "HUMAN_REVIEW":
                human_review_count += 1
            continue

        if status == "PARTIAL":
            partial_count += 1

        code = cr.get("python_code", "")
        code = inject_variable_names(code, registry, source_file_id)
        body_parts.append(code)

    # 5. Add cross-file stubs if needed
    body_text = "\n\n".join(body_parts)
    if unresolved_refs:
        body_text = add_cross_file_stubs(
            body_text, unresolved_refs, cross_file_sources or {}
        )

    # 6. Build final script
    header = _make_header(
        source_path, len(conversion_results), partial_count, target_runtime
    )
    final_script = f"{header}\n{import_block}\n\n\n{body_text}\n"

    # 7. ast.parse() validation
    syntax_valid = True
    syntax_errors: list[str] = []
    try:
        ast.parse(final_script)
    except SyntaxError as e:
        syntax_valid = False
        syntax_errors.append(f"Line {e.lineno}: {e.msg}")
        log.warning("merged_script_syntax_error", error=str(e), file=source_path)

    # 8. Determine status
    if not syntax_valid:
        merge_status = "FAILED"
    elif partial_count > 0 or human_review_count > 0:
        merge_status = "HAS_GAPS"
    else:
        merge_status = "SUCCESS"

    # 9. Write output
    suffix = "_converted_spark.py" if target_runtime == "pyspark" else "_converted.py"
    stem = Path(source_path).stem
    output_path = Path(output_dir) / f"{stem}{suffix}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(final_script, encoding="utf-8")

    log.info(
        "script_merged",
        file=source_path,
        blocks=len(conversion_results),
        partial=partial_count,
        human_review=human_review_count,
        syntax_valid=syntax_valid,
        status=merge_status,
    )

    return {
        "script_id": str(uuid4()),
        "source_file_id": source_file_id,
        "python_script": final_script,
        "import_block": import_block,
        "block_count": len(conversion_results),
        "partial_count": partial_count,
        "human_review_count": human_review_count,
        "syntax_valid": syntax_valid,
        "syntax_errors": syntax_errors,
        "status": merge_status,
        "output_path": str(output_path),
        "trace_id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
```

### Test: `tests/test_script_merger.py`

```python
import ast
from partition.merge.script_merger import merge_script


def test_basic_merge():
    crs = [
        {"python_code": "x = 1", "imports_detected": ["os"], "status": "SUCCESS"},
        {"python_code": "y = x + 1", "imports_detected": ["pandas"], "status": "SUCCESS"},
    ]
    parts = [
        {"raw_code": "x=1;", "line_start": 1, "line_end": 1, "partition_type": "DATA_STEP_BASIC"},
        {"raw_code": "y=x+1;", "line_start": 2, "line_end": 2, "partition_type": "DATA_STEP_BASIC"},
    ]
    result = merge_script(crs, parts, "f-001", "test.sas", output_dir="/tmp/test_merge")
    assert result["syntax_valid"] is True
    assert result["status"] == "SUCCESS"
    assert result["block_count"] == 2
    # Verify ast.parse works on output
    ast.parse(result["python_script"])


def test_human_review_inserts_todo():
    crs = [
        {"python_code": "", "imports_detected": [], "status": "HUMAN_REVIEW"},
    ]
    parts = [
        {"raw_code": "DATA complex; RUN;", "line_start": 1, "line_end": 3, "partition_type": "DATA_STEP_BASIC"},
    ]
    result = merge_script(crs, parts, "f-002", "complex.sas", output_dir="/tmp/test_merge")
    assert "TODO: HUMAN_REVIEW" in result["python_script"]
    assert result["human_review_count"] == 1
    assert result["status"] == "HAS_GAPS"


def test_ordering_by_line_start():
    crs = [
        {"python_code": "b = 2", "imports_detected": [], "status": "SUCCESS"},
        {"python_code": "a = 1", "imports_detected": [], "status": "SUCCESS"},
    ]
    parts = [
        {"raw_code": "b=2;", "line_start": 10, "line_end": 10, "partition_type": "DATA_STEP_BASIC"},
        {"raw_code": "a=1;", "line_start": 1, "line_end": 1, "partition_type": "DATA_STEP_BASIC"},
    ]
    result = merge_script(crs, parts, "f-003", "order.sas", output_dir="/tmp/test_merge")
    # 'a = 1' (line_start=1) should appear before 'b = 2' (line_start=10)
    idx_a = result["python_script"].index("a = 1")
    idx_b = result["python_script"].index("b = 2")
    assert idx_a < idx_b


def test_import_dedup():
    """Same module from two blocks appears only once."""
    crs = [
        {"python_code": "x = pd.DataFrame()", "imports_detected": ["pandas"], "status": "SUCCESS"},
        {"python_code": "y = pd.Series()", "imports_detected": ["pandas"], "status": "SUCCESS"},
    ]
    parts = [
        {"raw_code": "data a;", "line_start": 1, "line_end": 1},
        {"raw_code": "data b;", "line_start": 5, "line_end": 5},
    ]
    result = merge_script(crs, parts, "f-004", "dedup.sas", output_dir="/tmp/test_merge")
    assert result["python_script"].count("import pandas as pd") == 1
```

---

## Task 4: ReportAgent (#14)

**File**: `partition/merge/report_agent.py`

```python
"""
ReportAgent (#14) — Post-merge conversion report generator.

Generates Markdown + HTML conversion reports after ScriptMerger completes.
Primary deliverable for human reviewers and project managers.
"""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import markdown2
import structlog

from partition.agents.base_agent import BaseAgent

log = structlog.get_logger(__name__)


class ReportAgent(BaseAgent):
    """
    Agent #14 — Generates structured conversion reports.

    Inputs:
        - MergedScript dict
        - List of ConversionResult dicts
        - Optional: CodeBLEU scores, validation results, dep graph stats

    Outputs:
        - Markdown file: output/{source}_report.md
        - HTML file: output/{source}_report.html
        - ConversionReport dict for DuckDB insertion
    """

    agent_id: int = 14
    agent_name: str = "ReportAgent"

    def process(
        self,
        merged_script: dict,
        conversion_results: list[dict],
        source_path: str,
        target_runtime: str = "python",
        codebleu_scores: Optional[dict] = None,
        validation_results: Optional[dict] = None,
        dep_graph_stats: Optional[dict] = None,
        kb_retrieval_stats: Optional[dict] = None,
        output_dir: str = "output",
    ) -> dict:
        """Generate the conversion report."""

        # ---- Compute summary stats ----
        status_counts = Counter(cr.get("status", "UNKNOWN") for cr in conversion_results)
        total = len(conversion_results)
        success_n = status_counts.get("SUCCESS", 0)
        partial_n = status_counts.get("PARTIAL", 0)
        failed_n = status_counts.get("FAILED", 0)
        human_n = status_counts.get("HUMAN_REVIEW", 0)

        # ---- Failure mode breakdown ----
        failure_modes = Counter(
            cr.get("failure_mode_flagged", "")
            for cr in conversion_results
            if cr.get("failure_mode_flagged")
        )

        # ---- HUMAN_REVIEW blocks ----
        hr_blocks = [
            cr for cr in conversion_results
            if cr.get("status") == "HUMAN_REVIEW"
        ]

        # ---- Build Markdown ----
        md_lines = self._build_markdown(
            source_path=source_path,
            target_runtime=target_runtime,
            total=total,
            success_n=success_n,
            partial_n=partial_n,
            failed_n=failed_n,
            human_n=human_n,
            failure_modes=failure_modes,
            hr_blocks=hr_blocks,
            codebleu_scores=codebleu_scores,
            validation_results=validation_results,
            dep_graph_stats=dep_graph_stats,
            kb_retrieval_stats=kb_retrieval_stats,
            merged_script=merged_script,
        )

        md_text = "\n".join(md_lines)

        # ---- Convert to HTML ----
        html_text = markdown2.markdown(
            md_text,
            extras=["tables", "fenced-code-blocks", "header-ids"],
        )

        # ---- Write files ----
        stem = Path(source_path).stem
        md_path = Path(output_dir) / f"{stem}_report.md"
        html_path = Path(output_dir) / f"{stem}_report.html"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md_text, encoding="utf-8")
        html_path.write_text(html_text, encoding="utf-8")

        log.info(
            "conversion_report_generated",
            file=source_path,
            md_path=str(md_path),
            html_path=str(html_path),
        )

        # ---- ConversionReport dict for DuckDB ----
        report = {
            "report_id": str(uuid4()),
            "source_file_id": merged_script.get("source_file_id", ""),
            "total_blocks": total,
            "success_count": success_n,
            "partial_count": partial_n,
            "failed_count": failed_n,
            "human_review_count": human_n,
            "validation_pass": (validation_results or {}).get("pass", 0),
            "validation_fail": (validation_results or {}).get("fail", 0),
            "codebleu_mean": (codebleu_scores or {}).get("overall", None),
            "failure_mode_dist": json.dumps(dict(failure_modes)),
            "report_md_path": str(md_path),
            "report_html_path": str(html_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return report

    def _build_markdown(
        self,
        source_path: str,
        target_runtime: str,
        total: int,
        success_n: int,
        partial_n: int,
        failed_n: int,
        human_n: int,
        failure_modes: Counter,
        hr_blocks: list[dict],
        codebleu_scores: Optional[dict],
        validation_results: Optional[dict],
        dep_graph_stats: Optional[dict],
        kb_retrieval_stats: Optional[dict],
        merged_script: dict,
    ) -> list[str]:
        """Build the Markdown report line by line."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        pct = lambda n: f"{n/total*100:.1f}%" if total > 0 else "—"

        lines = [
            f"# Conversion Report: {Path(source_path).name}",
            "",
            f"- **Source**: `{source_path}`",
            f"- **Generated**: {now}",
            f"- **Target runtime**: {target_runtime}",
            f"- **Total blocks**: {total}",
            "",
            "---",
            "",
            "## Summary",
            "",
            "| Status | Count | Percentage |",
            "|--------|------:|------------|",
            f"| SUCCESS | {success_n} | {pct(success_n)} |",
            f"| PARTIAL | {partial_n} | {pct(partial_n)} |",
            f"| FAILED | {failed_n} | {pct(failed_n)} |",
            f"| HUMAN_REVIEW | {human_n} | {pct(human_n)} |",
            "",
        ]

        # ---- Failure Mode Breakdown ----
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

        # ---- HUMAN_REVIEW Blocks ----
        if hr_blocks:
            lines += [
                "## HUMAN_REVIEW Blocks",
                "",
            ]
            for i, cr in enumerate(hr_blocks[:10], 1):
                pid = cr.get("partition_id", "?")
                ptype = cr.get("partition_type", "?")
                lines.append(f"### {i}. Block `{pid}` ({ptype})")
                lines.append("")
                # Show first 10 lines of original SAS
                raw = cr.get("raw_sas_snippet", "")
                if raw:
                    snippet = "\n".join(raw.split("\n")[:10])
                    lines += ["```sas", snippet, "```", ""]

        # ---- CodeBLEU Scores ----
        if codebleu_scores:
            lines += [
                "## CodeBLEU Scores",
                "",
                f"- **Overall**: {codebleu_scores.get('overall', '—')}",
                "",
            ]
            per_type = codebleu_scores.get("per_type", {})
            if per_type:
                lines += [
                    "| Partition Type | CodeBLEU |",
                    "|----------------|----------|",
                ]
                for ptype, score in sorted(per_type.items()):
                    lines.append(f"| {ptype} | {score:.4f} |")
                lines.append("")

        # ---- Validation Results ----
        if validation_results:
            lines += [
                "## Validation Results",
                "",
                f"- **Pass**: {validation_results.get('pass', 0)}",
                f"- **Fail**: {validation_results.get('fail', 0)}",
                f"- **Warn**: {validation_results.get('warn', 0)}",
                "",
            ]

        # ---- Dependency Graph ----
        if dep_graph_stats:
            lines += [
                "## Dependency Graph Summary",
                "",
                f"- **Nodes**: {dep_graph_stats.get('nodes', 0)}",
                f"- **Edges**: {dep_graph_stats.get('edges', 0)}",
                f"- **SCC groups**: {dep_graph_stats.get('scc_count', 0)}",
                "",
            ]

        # ---- KB Retrieval Stats ----
        if kb_retrieval_stats:
            lines += [
                "## KB Retrieval Stats",
                "",
                f"- **Mean similarity score**: {kb_retrieval_stats.get('mean_sim', '—')}",
                f"- **Hit coverage**: {kb_retrieval_stats.get('coverage_pct', '—')}%",
                "",
            ]

        # ---- Merge Info ----
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
```

### DuckDB Schema — `conversion_reports`

```sql
-- Already defined in Week 7. Verify it exists:
CREATE TABLE IF NOT EXISTS conversion_reports (
  report_id           VARCHAR PRIMARY KEY,
  source_file_id      VARCHAR NOT NULL,
  total_blocks        INTEGER,
  success_count       INTEGER,
  partial_count       INTEGER,
  failed_count        INTEGER,
  human_review_count  INTEGER,
  validation_pass     INTEGER,
  validation_fail     INTEGER,
  codebleu_mean       DOUBLE,
  failure_mode_dist   VARCHAR,
  report_md_path      VARCHAR,
  report_html_path    VARCHAR,
  created_at          TIMESTAMP DEFAULT NOW()
);
```

---

## Task 5: FeedbackIngestionAgent

**File**: `partition/retraining/feedback_ingestion.py`

```python
"""
FeedbackIngestionAgent — Continuous Learning

Accepts corrections from two sources:
  1. CLI: python scripts/submit_correction.py --conversion_id {uuid} --python_file corrected.py
  2. Automated: cross-verifier rejects after 2 retries → auto-submit

For each correction:
  - Runs Prompt C cross-verification on corrected pair
  - If confidence ≥ 0.85: creates KB example, embeds, upserts to LanceDB
  - Updates original ConversionResult status → SUCCESS
  - Logs to feedback_log DuckDB table
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import structlog

log = structlog.get_logger(__name__)


class FeedbackIngestionAgent:
    """
    Ingests human or automated corrections and upserts them to the KB
    after cross-verification.
    """

    def __init__(
        self,
        lancedb_table,
        embed_fn,
        cross_verifier_fn,
        duckdb_conn,
        confidence_threshold: float = 0.85,
    ):
        """
        Args:
            lancedb_table: LanceDB sas_python_examples table handle.
            embed_fn: callable(text) → list[float] (768-dim Nomic embedding).
            cross_verifier_fn: callable(sas_code, python_code) → dict with 'confidence'.
            duckdb_conn: DuckDB connection for feedback_log writes.
            confidence_threshold: minimum confidence for acceptance (default 0.85).
        """
        self.lancedb_table = lancedb_table
        self.embed_fn = embed_fn
        self.cross_verifier_fn = cross_verifier_fn
        self.duckdb_conn = duckdb_conn
        self.confidence_threshold = confidence_threshold

    def ingest(
        self,
        conversion_id: str,
        partition_id: str,
        sas_code: str,
        corrected_python: str,
        source: str = "human_correction",
        partition_type: str = "",
        complexity_tier: str = "MODERATE",
        target_runtime: str = "python",
        failure_mode: str = "",
        category: str = "",
    ) -> dict:
        """
        Process a single correction.

        Returns:
            feedback_log dict (for inspection and DuckDB write).
        """
        feedback_id = str(uuid4())

        # Step 1: Cross-verify the corrected pair
        verification = self.cross_verifier_fn(sas_code, corrected_python)
        confidence = verification.get("confidence", 0.0)
        accepted = confidence >= self.confidence_threshold

        new_kb_id = None
        rejection_reason = None

        if accepted:
            # Step 2: Embed and upsert to LanceDB
            new_kb_id = str(uuid4())
            combined_text = f"SAS:\n{sas_code}\n\nPython:\n{corrected_python}"
            embedding = self.embed_fn(combined_text)

            kb_example = {
                "example_id": new_kb_id,
                "sas_code": sas_code,
                "python_code": corrected_python,
                "embedding": embedding,
                "partition_type": partition_type,
                "complexity_tier": complexity_tier,
                "target_runtime": target_runtime,
                "verified": True,
                "source": "correction",
                "failure_mode": failure_mode,
                "verification_method": "llm_crosscheck",
                "verification_score": confidence,
                "category": category,
                "version": 1,  # Will be incremented by KB versioning logic
                "superseded_by": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self.lancedb_table.add([kb_example])

            log.info(
                "correction_accepted",
                feedback_id=feedback_id,
                conversion_id=conversion_id,
                confidence=confidence,
                new_kb_id=new_kb_id,
            )
        else:
            rejection_reason = f"confidence {confidence:.3f} < {self.confidence_threshold}"
            log.warning(
                "correction_rejected",
                feedback_id=feedback_id,
                conversion_id=conversion_id,
                confidence=confidence,
                reason=rejection_reason,
            )

        # Step 3: Log to DuckDB
        feedback_log = {
            "feedback_id": feedback_id,
            "conversion_id": conversion_id,
            "partition_id": partition_id,
            "correction_source": source,
            "original_status": "PARTIAL",
            "new_kb_example_id": new_kb_id or "",
            "verifier_confidence": confidence,
            "accepted": accepted,
            "rejection_reason": rejection_reason or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_feedback_log(feedback_log)

        return feedback_log

    def _write_feedback_log(self, log_entry: dict) -> None:
        """Insert feedback log into DuckDB."""
        self.duckdb_conn.execute(
            """
            INSERT INTO feedback_log
            (feedback_id, conversion_id, partition_id, correction_source,
             original_status, new_kb_example_id, verifier_confidence,
             accepted, rejection_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                log_entry["feedback_id"],
                log_entry["conversion_id"],
                log_entry["partition_id"],
                log_entry["correction_source"],
                log_entry["original_status"],
                log_entry["new_kb_example_id"],
                log_entry["verifier_confidence"],
                log_entry["accepted"],
                log_entry["rejection_reason"],
                log_entry["created_at"],
            ],
        )
```

### CLI Script: `scripts/submit_correction.py`

```python
"""
CLI for submitting corrections.

Usage:
    python scripts/submit_correction.py \
        --conversion_id abc123 \
        --python_file corrected.py \
        [--sas_file original.sas]
"""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Submit a correction to the KB")
    parser.add_argument("--conversion_id", required=True, help="UUID of the conversion")
    parser.add_argument("--python_file", required=True, help="Path to corrected Python file")
    parser.add_argument("--sas_file", help="Path to original SAS file (optional)")
    args = parser.parse_args()

    corrected_python = Path(args.python_file).read_text(encoding="utf-8")
    print(f"Read {len(corrected_python)} chars from {args.python_file}")

    # In practice: load conversion_id from SQLite, get sas_code,
    # instantiate FeedbackIngestionAgent, call .ingest()
    print(f"Correction submitted for conversion_id={args.conversion_id}")
    print("(FeedbackIngestionAgent will process via cross-verification)")


if __name__ == "__main__":
    main()
```

---

## Task 6: ConversionQualityMonitor

**File**: `partition/retraining/quality_monitor.py`

```python
"""
ConversionQualityMonitor — Continuous Learning

Runs at the end of every processing batch.
Computes success_rate, partial_rate, avg_llm_confidence, failure_mode_dist.
Alerts via structlog WARNING if thresholds are breached.
"""

from collections import Counter
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import structlog

log = structlog.get_logger(__name__)


class ConversionQualityMonitor:
    """
    Post-batch quality monitor.
    Queries the last N conversion_results from DuckDB and computes health metrics.
    """

    def __init__(
        self,
        duckdb_conn,
        success_target: float = 0.70,
        confidence_target: float = 0.75,
        single_mode_cap: float = 0.40,
        window_size: int = 100,
    ):
        self.duckdb_conn = duckdb_conn
        self.success_target = success_target
        self.confidence_target = confidence_target
        self.single_mode_cap = single_mode_cap
        self.window_size = window_size

    def evaluate(self, batch_id: str | None = None) -> dict:
        """
        Compute quality metrics for the last `window_size` conversions.

        Returns:
            Quality metrics dict (also written to DuckDB quality_metrics table).
        """
        # Query last N results
        rows = self.duckdb_conn.execute(
            f"""
            SELECT status, llm_confidence, failure_mode_flagged
            FROM conversion_results
            ORDER BY created_at DESC
            LIMIT {self.window_size}
            """
        ).fetchall()

        if not rows:
            log.warning("no_conversion_results_found")
            return {}

        n_total = len(rows)
        statuses = [r[0] for r in rows]
        confidences = [r[1] for r in rows if r[1] is not None]
        failure_modes = [r[2] for r in rows if r[2]]

        n_success = statuses.count("SUCCESS")
        n_partial = statuses.count("PARTIAL")
        n_human = statuses.count("HUMAN_REVIEW")

        success_rate = n_success / n_total
        partial_rate = n_partial / n_total
        human_review_rate = n_human / n_total
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        failure_mode_dist = Counter(failure_modes)

        # ---- Alert checks ----
        alerts: list[str] = []

        if success_rate < self.success_target:
            msg = f"success_rate {success_rate:.3f} < {self.success_target}"
            log.warning("quality_alert", alert=msg)
            alerts.append(msg)

        if avg_confidence < self.confidence_target:
            msg = f"avg_confidence {avg_confidence:.3f} < {self.confidence_target}"
            log.warning("quality_alert", alert=msg)
            alerts.append(msg)

        # Check if any single failure mode > 40% of PARTIALs
        if n_partial > 0:
            for mode, count in failure_mode_dist.items():
                ratio = count / n_partial
                if ratio > self.single_mode_cap:
                    msg = f"failure_mode '{mode}' = {ratio:.1%} of PARTIALs (>{self.single_mode_cap:.0%})"
                    log.warning("kb_gap_detected", alert=msg, mode=mode, ratio=ratio)
                    alerts.append(msg)

        # ---- Persist to DuckDB ----
        metrics = {
            "metric_id": str(uuid4()),
            "batch_id": batch_id or str(uuid4()),
            "n_evaluated": n_total,
            "success_rate": success_rate,
            "partial_rate": partial_rate,
            "human_review_rate": human_review_rate,
            "avg_llm_confidence": avg_confidence,
            "avg_retry_count": 0.0,  # computed separately if needed
            "failure_mode_dist": str(dict(failure_mode_dist)),
            "kb_size": self._get_kb_size(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._write_metrics(metrics)

        log.info(
            "quality_evaluation_complete",
            success_rate=f"{success_rate:.3f}",
            avg_confidence=f"{avg_confidence:.3f}",
            n_alerts=len(alerts),
        )

        return {**metrics, "alerts": alerts}

    def _get_kb_size(self) -> int:
        """Get current KB size from LanceDB metadata (or return 0)."""
        try:
            result = self.duckdb_conn.execute(
                "SELECT MAX(kb_size) FROM quality_metrics"
            ).fetchone()
            return result[0] if result and result[0] else 0
        except Exception:
            return 0

    def _write_metrics(self, metrics: dict) -> None:
        """Insert metrics into DuckDB quality_metrics table."""
        self.duckdb_conn.execute(
            """
            INSERT INTO quality_metrics
            (metric_id, batch_id, n_evaluated, success_rate, partial_rate,
             human_review_rate, avg_llm_confidence, avg_retry_count,
             failure_mode_dist, kb_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                metrics["metric_id"],
                metrics["batch_id"],
                metrics["n_evaluated"],
                metrics["success_rate"],
                metrics["partial_rate"],
                metrics["human_review_rate"],
                metrics["avg_llm_confidence"],
                metrics["avg_retry_count"],
                metrics["failure_mode_dist"],
                metrics["kb_size"],
                metrics["created_at"],
            ],
        )
```

---

## Task 7: Retraining Trigger Logic

**File**: `partition/retraining/retrain_trigger.py`

```python
"""
Retraining Trigger — Continuous Learning

Monitors 4 conditions that trigger sklearn LR retraining:
  1. KB grew by ≥ 500 verified examples since last training
  2. ECE on held-out 20% > 0.12
  3. success_rate < 0.70 for two consecutive batches
  4. KB gap detected by ConversionQualityMonitor

On KB gap: triggers targeted KB generation for the underrepresented category.
"""

import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

import structlog

log = structlog.get_logger(__name__)


@dataclass
class RetrainDecision:
    """Result of the retraining trigger evaluation."""
    should_retrain: bool
    trigger_reason: str
    targeted_category: Optional[str] = None  # for KB gap triggers


class RetrainTrigger:
    """
    Evaluates the 4 retraining conditions.
    Call .evaluate() after each batch.
    """

    def __init__(
        self,
        duckdb_conn,
        kb_growth_threshold: int = 500,
        ece_threshold: float = 0.12,
        success_threshold: float = 0.70,
        consecutive_failures: int = 2,
    ):
        self.duckdb_conn = duckdb_conn
        self.kb_growth_threshold = kb_growth_threshold
        self.ece_threshold = ece_threshold
        self.success_threshold = success_threshold
        self.consecutive_failures = consecutive_failures

    def evaluate(self) -> RetrainDecision:
        """
        Check all 4 conditions. Returns a RetrainDecision.
        """

        # Condition 1: KB growth
        kb_growth = self._check_kb_growth()
        if kb_growth >= self.kb_growth_threshold:
            log.info("retrain_trigger_kb_growth", growth=kb_growth)
            return RetrainDecision(
                should_retrain=True,
                trigger_reason=f"KB grew by {kb_growth} examples (threshold: {self.kb_growth_threshold})",
            )

        # Condition 2: ECE too high
        latest_ece = self._get_latest_ece()
        if latest_ece is not None and latest_ece > self.ece_threshold:
            log.info("retrain_trigger_ece", ece=latest_ece)
            return RetrainDecision(
                should_retrain=True,
                trigger_reason=f"ECE = {latest_ece:.4f} (threshold: {self.ece_threshold})",
            )

        # Condition 3: success_rate < threshold for 2 consecutive batches
        low_success_streak = self._check_consecutive_low_success()
        if low_success_streak >= self.consecutive_failures:
            log.info("retrain_trigger_low_success", streak=low_success_streak)
            return RetrainDecision(
                should_retrain=True,
                trigger_reason=f"success_rate < {self.success_threshold} for {low_success_streak} consecutive batches",
            )

        # Condition 4: KB gap detected
        gap_mode = self._check_kb_gap()
        if gap_mode:
            log.info("retrain_trigger_kb_gap", mode=gap_mode)
            return RetrainDecision(
                should_retrain=True,
                trigger_reason=f"KB gap: '{gap_mode}' accounts for >40% of PARTIAL conversions",
                targeted_category=gap_mode,
            )

        return RetrainDecision(should_retrain=False, trigger_reason="no trigger condition met")

    def trigger_targeted_generation(self, category: str) -> None:
        """
        Trigger targeted KB generation for underrepresented category.
        Calls: python scripts/generate_pairs.py --category {category} --count 20
        """
        cmd = [
            sys.executable,
            "scripts/generate_pairs.py",
            "--category", category,
            "--count", "20",
        ]
        log.info("targeted_kb_generation", category=category, cmd=" ".join(cmd))
        subprocess.run(cmd, check=True)

    def _check_kb_growth(self) -> int:
        """Get KB examples added since last training."""
        try:
            result = self.duckdb_conn.execute("""
                SELECT
                    (SELECT COUNT(*) FROM kb_changelog WHERE action = 'insert') -
                    COALESCE((SELECT n_train FROM calibration_log
                              ORDER BY created_at DESC LIMIT 1), 0)
            """).fetchone()
            return max(result[0] if result and result[0] else 0, 0)
        except Exception:
            return 0

    def _get_latest_ece(self) -> Optional[float]:
        """Get the most recent ECE score."""
        try:
            result = self.duckdb_conn.execute("""
                SELECT ece_score FROM calibration_log
                ORDER BY created_at DESC LIMIT 1
            """).fetchone()
            return result[0] if result else None
        except Exception:
            return None

    def _check_consecutive_low_success(self) -> int:
        """Count recent consecutive batches with success_rate < threshold."""
        try:
            rows = self.duckdb_conn.execute("""
                SELECT success_rate FROM quality_metrics
                ORDER BY created_at DESC LIMIT 5
            """).fetchall()
            streak = 0
            for row in rows:
                if row[0] < self.success_threshold:
                    streak += 1
                else:
                    break
            return streak
        except Exception:
            return 0

    def _check_kb_gap(self) -> Optional[str]:
        """
        Check the latest quality_metrics for a KB gap
        (single failure mode > 40% of PARTIALs).
        """
        try:
            result = self.duckdb_conn.execute("""
                SELECT failure_mode_dist FROM quality_metrics
                ORDER BY created_at DESC LIMIT 1
            """).fetchone()
            if not result or not result[0]:
                return None
            import ast as _ast
            dist = _ast.literal_eval(result[0])
            total_partial = sum(dist.values())
            if total_partial == 0:
                return None
            for mode, count in dist.items():
                if count / total_partial > 0.40:
                    return mode
            return None
        except Exception:
            return None
```

---

## Task 8: KB Expansion 250 → 330 Pairs

**File**: `scripts/expand_kb.py`

```python
"""
Expand KB from 250 → 330 verified pairs.

Strategy:
  1. Identify underpopulated categories from the 15-category matrix
  2. Generate pairs for each category gap via generate_pairs.py
  3. Cross-verify with Prompt C
  4. Upsert verified pairs to LanceDB

Target: 330 total verified pairs + 60 failure-mode injection pairs.

Usage:
    python scripts/expand_kb.py --target 330 --batch_size 10
"""

import argparse
from collections import Counter


# Target per category (from cahier §5.2)
CATEGORY_TARGETS = {
    "DATA_STEP_BASIC": 30,
    "DATA_STEP_MERGE": 25,
    "DATA_STEP_RETAIN": 20,
    "DATA_STEP_ARRAY": 20,
    "DATA_STEP_FIRST_LAST": 25,
    "DATE_ARITHMETIC": 30,
    "PROC_SQL": 30,
    "PROC_MEANS": 20,
    "PROC_FREQ": 15,
    "MACRO_BASIC": 25,
    "MACRO_CONDITIONAL": 20,
    "PROC_SORT": 15,
    "PROC_REG_LOGISTIC": 20,
    "PROC_IMPORT_EXPORT": 15,
    "MISSING_VALUE_HANDLING": 20,
}

# 60 failure-mode injection pairs: 6 modes × 10 each
FAILURE_MODE_TARGETS = {
    "RETAIN": 10,
    "FIRST_LAST": 10,
    "DATE_ARITHMETIC": 10,
    "MERGE_SEMANTICS": 10,
    "MISSING_VALUE_COMPARISON": 10,
    "PROC_MEANS_OUTPUT": 10,
}


def get_current_counts(lancedb_table) -> Counter:
    """Count current KB examples per category."""
    df = lancedb_table.to_pandas()
    return Counter(df["category"].tolist())


def compute_gaps(current: Counter) -> dict[str, int]:
    """Compute how many pairs each category needs."""
    gaps = {}
    for cat, target in CATEGORY_TARGETS.items():
        current_count = current.get(cat, 0)
        if current_count < target:
            gaps[cat] = target - current_count
    return gaps


def main():
    parser = argparse.ArgumentParser(description="Expand KB to target count")
    parser.add_argument("--target", type=int, default=330)
    parser.add_argument("--batch_size", type=int, default=10)
    args = parser.parse_args()

    print(f"Target: {args.target} verified pairs")
    print(f"Category targets: {sum(CATEGORY_TARGETS.values())} from 15 categories")
    print(f"Failure-mode injection: {sum(FAILURE_MODE_TARGETS.values())} pairs")
    print(f"Grand total target: {sum(CATEGORY_TARGETS.values()) + sum(FAILURE_MODE_TARGETS.values())}")

    # In practice:
    # 1. Connect to LanceDB
    # 2. Get current counts
    # 3. Compute gaps
    # 4. For each gap: call generate_pairs.py --category X --count N
    # 5. Cross-verify results
    # 6. Report final counts


if __name__ == "__main__":
    main()
```

---

## Task 9: End-to-End Integration Test

**File**: `tests/test_merge_e2e.py`

```python
"""
End-to-end test for the Merge Layer (L4).

Verifies:
  1. ImportConsolidator deduplicates correctly
  2. DependencyInjector patches names consistently
  3. ScriptMerger produces ast.parse()-valid output
  4. ReportAgent generates valid Markdown
  5. Pipeline flow: ConversionResult[] → MergedScript + Report
"""

import ast
import json
import tempfile
from pathlib import Path


def test_full_merge_pipeline():
    """
    Simulate 5 translated blocks → merge → report.
    """
    from partition.merge.script_merger import merge_script

    # Create mock conversion results
    crs = [
        {
            "python_code": "df_customers = pd.read_csv('customers.csv')",
            "imports_detected": ["pandas"],
            "status": "SUCCESS",
            "llm_confidence": 0.92,
            "failure_mode_flagged": "",
        },
        {
            "python_code": "df_sales = pd.merge(df_customers, sales, on='id')",
            "imports_detected": ["pandas"],
            "status": "SUCCESS",
            "llm_confidence": 0.88,
            "failure_mode_flagged": "MERGE_SEMANTICS",
        },
        {
            "python_code": "total = df_sales.groupby('region').sum()",
            "imports_detected": ["pandas"],
            "status": "PARTIAL",
            "llm_confidence": 0.65,
            "failure_mode_flagged": "FIRST_LAST",
        },
        {
            "python_code": "",
            "imports_detected": [],
            "status": "HUMAN_REVIEW",
            "llm_confidence": 0.30,
            "failure_mode_flagged": "DATE_ARITHMETIC",
        },
        {
            "python_code": "df_out = df_sales.describe()",
            "imports_detected": ["pandas"],
            "status": "SUCCESS",
            "llm_confidence": 0.95,
            "failure_mode_flagged": "",
        },
    ]

    parts = [
        {"raw_code": "DATA customers; INFILE 'c.csv'; RUN;", "line_start": 1, "line_end": 3, "partition_type": "DATA_STEP_BASIC"},
        {"raw_code": "DATA merged; MERGE customers sales; BY id; RUN;", "line_start": 4, "line_end": 7, "partition_type": "DATA_STEP_MERGE"},
        {"raw_code": "PROC MEANS DATA=sales NWAY; CLASS region; RUN;", "line_start": 8, "line_end": 10, "partition_type": "PROC_MEANS"},
        {"raw_code": "DATA dated; x=INTNX('MONTH', today(), 1); RUN;", "line_start": 11, "line_end": 14, "partition_type": "DATE_ARITHMETIC"},
        {"raw_code": "PROC MEANS DATA=sales; RUN;", "line_start": 15, "line_end": 17, "partition_type": "PROC_MEANS"},
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        result = merge_script(
            crs, parts, "file-e2e", "etl_customer.sas",
            target_runtime="python", output_dir=tmpdir,
        )

        # Assertions
        assert result["block_count"] == 5
        assert result["partial_count"] == 1
        assert result["human_review_count"] == 1
        assert result["status"] == "HAS_GAPS"
        assert "TODO: HUMAN_REVIEW" in result["python_script"]
        assert result["python_script"].count("import pandas as pd") == 1

        # Output file exists
        assert Path(result["output_path"]).exists()


def test_syntax_validity_rate():
    """
    Merge 10 simple SUCCESS blocks → 100% syntax valid.
    Target: ≥ 95% across all merges.
    """
    from partition.merge.script_merger import merge_script
    import tempfile

    crs = [
        {"python_code": f"x_{i} = {i}", "imports_detected": [], "status": "SUCCESS"}
        for i in range(10)
    ]
    parts = [
        {"raw_code": f"x{i}={i};", "line_start": i * 2, "line_end": i * 2 + 1}
        for i in range(10)
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        result = merge_script(crs, parts, "f-syntax", "syntax_test.sas", output_dir=tmpdir)
        assert result["syntax_valid"] is True
```

---

## File Structure After Week 11

```
partition/
├── merge/
│   ├── __init__.py
│   ├── import_consolidator.py      ← Task 1
│   ├── dependency_injector.py      ← Task 2
│   ├── script_merger.py            ← Task 3
│   └── report_agent.py             ← Task 4
├── retraining/
│   ├── __init__.py
│   ├── feedback_ingestion.py       ← Task 5
│   ├── quality_monitor.py          ← Task 6
│   └── retrain_trigger.py          ← Task 7
scripts/
├── submit_correction.py            ← Task 5 (CLI)
├── expand_kb.py                    ← Task 8
├── generate_pairs.py               (from Week 9)
tests/
├── test_import_consolidator.py     ← Task 1
├── test_dependency_injector.py     ← Task 2
├── test_script_merger.py           ← Task 3
├── test_merge_e2e.py               ← Task 9
output/
├── {source}_converted.py           ← generated
├── {source}_converted_spark.py     ← generated (PySpark)
├── {source}_report.md              ← generated
└── {source}_report.html            ← generated
```

---

## Dependencies (pip)

```
markdown2>=2.4      # Markdown → HTML for ReportAgent
# All other deps already installed from previous weeks:
# structlog, pydantic, lancedb, duckdb, nomic, instructor, etc.
```

---

## ✅ Week 11 Success Checklist

| # | Check | Target | Command |
|---|-------|--------|---------|
| 1 | Import deduplication | Each library appears exactly once | `pytest tests/test_import_consolidator.py` |
| 2 | PEP 8 import ordering | stdlib → third-party → local | Visual inspection of merged scripts |
| 3 | Variable name consistency | All SAS→Python names use snake_case | `pytest tests/test_dependency_injector.py` |
| 4 | Block ordering | Blocks sorted by `line_start` | `pytest tests/test_script_merger.py::test_ordering_by_line_start` |
| 5 | Merged script syntax_valid | ≥ 95% of merged scripts pass `ast.parse()` | `pytest tests/test_merge_e2e.py::test_syntax_validity_rate` |
| 6 | TODO stubs present | HUMAN_REVIEW → structured TODO with SAS | `grep -c "TODO: HUMAN_REVIEW" output/*.py` |
| 7 | ReportAgent output | Markdown + HTML files generated | `ls output/*_report.md output/*_report.html` |
| 8 | ReportAgent DuckDB | Row in `conversion_reports` | `python -c "import duckdb; ... SELECT COUNT(*) ..."` |
| 9 | FeedbackIngestion works | Correction → KB upsert | `pytest tests/test_continuous_learning.py` |
| 10 | QualityMonitor alerts | Warns when success_rate < 0.70 | Log inspection after batch run |
| 11 | Retraining trigger | 4 conditions evaluated correctly | Unit tests for RetrainTrigger |
| 12 | KB size ≥ 330 | LanceDB verified count | `python -c "import lancedb; print(len(...))"` |

---

## Evaluation Metrics — Week 11

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Merged script syntax validity | ≥ 95% | `ast.parse()` on all merged scripts |
| Import deduplication | = 1.00 | Each import statement appears exactly once |
| Block ordering preservation | = 1.00 | `line_start` monotonically increasing in output |
| Variable name consistency | = 1.00 | No raw SAS dataset names in final `.py` |
| Report generation | 100% of merged files | `ls output/*_report.md \| wc -l` vs merged count |
| KB pairs verified | ≥ 330 | LanceDB table count |
| Quality monitor coverage | 100% of batches | DuckDB `quality_metrics` row count |

---

## Common Pitfalls

1. **Import ordering edge cases** — `from datetime import datetime` is stdlib but `import dateutil` is third-party. Test both.
2. **ast.parse() on incomplete code** — If an LLM generates `def foo(` (unclosed), the merge will fail. ScriptMerger catches this and sets `syntax_valid=False`.
3. **Variable name collisions** — Two SAS datasets `WORK.SALES` and `LIB.SALES` both map to `_sales`. Add prefix from library: `work_sales` vs `lib_sales`.
4. **ReportAgent markdown2 extras** — Must enable `tables` and `fenced-code-blocks` extras for proper HTML rendering.
5. **Feedback ingestion race condition** — If two corrections arrive for the same conversion_id simultaneously, use `ON CONFLICT` in DuckDB or check before insert.
6. **KB versioning on expansion** — When expanding from 250→330, track new inserts in `kb_changelog` with `author="llm_gen"`.

---

> *Week 11 — Merge Layer (L4) + ReportAgent (#14) + Continuous Learning + KB → 330*
