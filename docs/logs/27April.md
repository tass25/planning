# 27 April 2026 — Session Log

## Output Path Fix: CSVs & Charts Write to `./output/`

### Problem
Translated Python code preserved hardcoded SAS paths (e.g., `/output/migration_validation_2024SEP20.csv`, `C:\data\report.xlsx`). When users downloaded and ran the converted script, file writes would fail or land in system directories. Charts using `plt.show()` produced no files at all.

### Changes

**1. `backend/api/services/translation_service.py` — `_auto_repair()`**
- Added regex to rewrite absolute Unix paths (`/any/path/file.csv`) → `./output/file.csv`
- Added regex to rewrite absolute Windows paths (`C:\any\path\file.csv`) → `./output/file.csv`
- Upgraded `plt.show()` replacement to write to `./output/chart_N.png` (was bare `chart_N.png`)
- Added regex to redirect bare `plt.savefig('file.png')` calls → `./output/file.png`
- Protected already-correct `./output/` paths from double-rewriting

**2. `backend/partition/translation/deterministic_translator.py` — `_try_proc_export()`**
- PROC EXPORT now strips directory from SAS OUTFILE path and writes to `./output/filename`
- Before: `df.to_csv('/output/migration.csv')` → After: `df.to_csv('./output/migration.csv')`

**3. `backend/api/services/pipeline_service.py` — merge stage header**
- Injected `import os; os.makedirs('./output', exist_ok=True)` at top of every converted script
- Injected `import matplotlib; matplotlib.use('Agg')` when chart code is detected (non-interactive backend)

### Test Results
```
10/10 custom path-rewriting tests passed:
  - Unix absolute path rewrite
  - Windows path (forward slash)
  - Windows path (backslash)
  - Nested Unix path flattened to ./output/
  - plt.show() → savefig to ./output/
  - Bare savefig filename redirected
  - No double-rewrite on already-correct paths
  - Deterministic PROC EXPORT path fix
  - URL not accidentally rewritten
  - Sequential chart numbering (chart_1.png, chart_2.png)

Existing test suites:
  - test_critical_paths.py: 8/8 passed
  - test_boundary_detector.py: 14/14 passed
  - test_streaming.py: 8/8 passed
```
