# Merge Layer (L4) — `partition/merge/`

Assembles translated partitions into complete Python scripts.

## Modules

| Module | Purpose |
|---|---|
| `import_consolidator.py` | Deduplicates imports, applies PEP 8 ordering (stdlib → third-party → local), maps canonical aliases |
| `dependency_injector.py` | Resolves SAS dataset names → Python variable names, injects cross-file stubs |
| `script_merger.py` | Orchestrates merge: sorts by line_start, consolidates imports, injects names, validates via `ast.parse()` |
| `report_agent.py` | **Agent #14** – Generates Markdown + HTML conversion reports with summary tables, failure mode breakdown, CodeBLEU |

## Data Flow

```
ConversionResult[] ──► ImportConsolidator ──► import block
                   ──► DependencyInjector ──► name registry
                   ──► ScriptMerger       ──► final .py file + MergedScript dict
                   ──► ReportAgent        ──► Markdown + HTML reports
```

## Usage

```python
from partition.merge.script_merger import merge_script
from partition.merge.report_agent import ReportAgent

merged = merge_script(conversion_results, partitions, file_id, "input.sas")
report = ReportAgent().generate_report(file_id, "input.sas", merged, conversion_results)
```
