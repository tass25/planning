# Week 1–2 Done: L2-A — Project Scaffold, Entry Agents & Gold Standard Corpus

> **Dates**: Feb 19, 2026
> **Layer**: L2-A (Entry & Scan)
> **Branch**: `main`
> **Commits**: `fa9e2dd` → `d62e52c` → `532f8a9` → `cd7ef56` → `4b49f2d` → `52cd7f2` → `713efab` → `c179c3c` → `972ed8e` → `b2b2dd4`

---

## 🎯 Objective

Bootstrap the entire project from zero: directory structure, base classes, three L2-A agents, a SQLite persistence layer, and a 50-file gold-standard SAS corpus with 721 manually annotated block boundaries across three complexity tiers (simple / medium / hard).

---

## ✅ What Was Done

### 1. Project Scaffold (`94882c0`, `4410fd2`)

Created the full monorepo skeleton in `sas_converter/`:

```
sas_converter/
├── partition/
│   ├── base_agent.py          ← BaseAgent ABC (async process())
│   ├── logging_config.py      ← structlog JSON logging
│   ├── models/
│   │   ├── enums.py           ← PartitionType (9 values), RiskLevel, ConversionStatus
│   │   ├── partition_ir.py    ← PartitionIR Pydantic v2 model
│   │   └── file_metadata.py   ← FileMetadata Pydantic v2 model
│   ├── entry/
│   │   ├── file_analysis_agent.py
│   │   ├── cross_file_dep_resolver.py
│   │   └── registry_writer_agent.py
│   └── db/
│       └── sqlite_manager.py  ← SQLAlchemy async engine
├── tests/
├── knowledge_base/gold_standard/
├── config/project_config.yaml
├── requirements.txt
└── README.md
```

**Key design choices**:
- `BaseAgent` is an abstract class with a single abstract async method `process()`. All later agents inherit from it, ensuring a uniform interface.
- `PartitionIR` uses Pydantic v2, enforcing schema validation at runtime.
- `enums.py` defines `PartitionType` with 9 values: `DATA_STEP`, `PROC_BLOCK`, `SQL_BLOCK`, `MACRO_DEFINITION`, `MACRO_INVOCATION`, `CONDITIONAL_BLOCK`, `LOOP_BLOCK`, `GLOBAL_STATEMENT`, `INCLUDE_STATEMENT`.

---

### 2. L2-A Agents

#### FileAnalysisAgent
- Scans a directory for `.sas` files recursively.
- Detects file encoding with `chardet` (UTF-8 / Latin-1 / Windows-1252 common in legacy SAS).
- Computes SHA-256 hash for each file to detect duplicates.
- Returns a list of `FileMetadata` objects.

#### CrossFileDependencyResolver
- Parses `%INCLUDE` and `LIBNAME` statements to detect inter-file dependencies.
- Builds a directed dependency graph (adjacency dict).
- Detects circular includes (would cause infinite recursion in the converter).

#### RegistryWriterAgent
- Persists `FileMetadata` objects to a SQLite DB via SQLAlchemy.
- Creates the `file_registry` table on first run.
- Uses upsert logic (UPDATE OR INSERT) to be idempotent.

#### DataLineageExtractor (`52cd7f2`)
- Parses `DATA` step `SET`/`MERGE`/`UPDATE` statements and `PROC` step `DATA=` options to extract table-level read/write lineage.
- Writes to a `data_lineage` table: `(source_file, source_table, target_table, lineage_type)`.
- Passes 5 unit tests.

---

### 3. Gold Standard Corpus (`e50fff9` → `c179c3c`)

Built a 50-file annotated corpus split across 3 complexity tiers:

| Tier | Files | Blocks | Description |
|------|-------|--------|-------------|
| Simple (`gs_*`) | gs\_01–gs\_50 | ~350 | Single-type blocks, clean boundaries |
| Medium (`gsm_*`) | gsm\_06–gsm\_20 | ~220 | Mixed types, macro interleaving |
| Hard (`gsh_*`) | gsh\_01–gsh\_15 | ~151 | Deep nesting, CALL EXECUTE, ambiguous boundaries |
| **Total** | **50 .sas + 50 .gold.json** | **721** | |

Each `.gold.json` file follows the schema:
```json
{
  "file": "gs_01.sas",
  "tier": "simple",
  "blocks": [
    { "block_type": "DATA_STEP", "line_start": 1, "line_end": 8 },
    ...
  ]
}
```

**Why a gold corpus?** The boundary detector (L2-B/C) needed a ground truth to benchmark against. Manual annotation was the only reliable approach for ambiguous SAS constructs.

---

### 4. Benchmark Infrastructure

No automated benchmark yet (created in week 3–4), but the gold corpus was the prerequisite. All 50 gold JSON files were validated for:
- No overlapping blocks
- `line_end >= line_start`
- All block types valid enum values

---

## ❌ Errors & Struggles

### Error 1: `line_end` off-by-one in gold JSONs (`b2b2dd4`)

**Problem**: When annotating gold blocks by hand, `line_end` was recorded as the last line of actual code, not including the trailing `RUN;` or `QUIT;` in some cases. This caused a systematic off-by-one where the gold block ended 1 line before the real end.

**Symptom**: Early boundary-accuracy calculations showed many "close" blocks (delta=1) being counted as misses.

**Solution**: Created a fix pass over all gold JSONs to re-check each `line_end`. Added a tolerance parameter `TOLERANCE=2` to the benchmark (a detected block counts as matched if `|detected_start - gold_start| ≤ 2` AND `|detected_end - gold_end| ≤ 2`).

---

### Error 2: `PROC SQL` annotated as `PROC_SQL` instead of `SQL_BLOCK` (`972ed8e`)

**Problem**: Several gold JSONs used type `"PROC_SQL"` or `"PROC_SQLSQL_BLOCK"` (a concatenation artifact from copy-paste) instead of the canonical `"SQL_BLOCK"`.

**Symptom**: Pydantic validation raised `ValueError: 'PROC_SQL' is not a valid PartitionType` when loading gold files in tests.

**Solution**: Wrote a one-off fix script that regex-replaced `"PROC_SQL"` and `"PROC_SQLSQL_BLOCK"` → `"SQL_BLOCK"` across all 50 gold JSON files. Added validation in the gold-loader to raise a clear error if an unknown type appears.

---

### Error 3: `asyncio.get_event_loop()` deprecation in Python 3.10 (`972ed8e`)

**Problem**: Tests used `asyncio.get_event_loop().run_until_complete(coro)` to run async agents synchronously. Python 3.10 deprecated creating a new event loop implicitly, causing `DeprecationWarning` on every test run.

**Symptom**: `DeprecationWarning: There is no current event loop` printed 15 times during `pytest`.

**Solution**: Replaced with `asyncio.run(coro)` in test helpers. Added a note to the project checklist that all new test files must use `asyncio.run()`.  
*(Note: the older `test_boundary_detector.py` still uses the deprecated pattern as of the end of this project — it was not blocking any CI pass.)*

---

### Error 4: `from __future__ import annotations` missing (`6e4f7d1`)

**Problem**: Several modules used `list[X]` and `dict[X, Y]` type hints in Python 3.10, which caused `TypeError` at import time on some edge cases because the `postponed annotations` behaviour wasn't activated.

**Solution**: Added `from __future__ import annotations` to all 8 module files in a single clean-up commit.

---

### Error 5: Hard-tier corpus underrepresented in early draft

**Problem**: The initial gold corpus only had 35 simple + medium files. Hard files (`gsh_*`) with CALL EXECUTE patterns and deeply nested `%DO` loops were not yet covered. This would have created a biased benchmark.

**Solution**: Spent additional time creating `gsh_01` through `gsh_15` by hand, pulling representative patterns from real production SAS scripts. The hard tier became the primary stress-test set for the boundary detector.

---

## 📊 Outputs & Results

| Metric | Value |
|--------|-------|
| L2-A agents implemented | 4 (FileAnalysis, CrossFileDep, RegistryWriter, DataLineage) |
| Unit tests | 15 (all passing) |
| Gold standard files | 50 `.sas` + 50 `.gold.json` |
| Total annotated blocks | **721** |
| Tier breakdown | Simple: ~350 / Medium: ~220 / Hard: ~151 |
| Boundary benchmark score | N/A (benchmark not yet built) |
| Lines of production code | ~875 |

---

## 💡 Key Learnings

- Hand-annotating 721 SAS blocks is tedious but unavoidable — SAS boundary rules are complex enough that no existing tool gives reliable ground truth.
- Pydantic v2's strict enum validation caught annotation errors early; worth the setup cost.
- The `TOLERANCE=2` heuristic in the benchmark was essential: SAS comment blocks before a `DATA` step legitimately belong to it, so the "true" start is ambiguous by ±1–2 lines.

---

## 📊 Visualization Script (Added 2026-03-03)

**File**: `planning/week01_02viz.py`

**Purpose**: Interactive visualization of Week 1-2 deliverables (file registry, cross-file dependencies, data lineage).

**What it shows**:
- File registry stats (encoding distribution, line counts)
- NetworkX dependency graph with spring layout
- Data lineage flow diagram (dataset-prefix color coding: raw.*/staging.*/mart.*)

**Database required**: `file_registry.db` (SQLite)

**Setup**:
```bash
# Generate empty database schema
python setup_viz_data.py

# Populate with dummy test data
python populate_dummy_data.py

# OR populate with real data
python main.py --dir sas_converter/knowledge_base/gold_standard/
```

**Run**:
```bash
python planning/week01_02viz.py
```

**Output**: Text summary + matplotlib plots showing file registry metrics and dependency graphs.
