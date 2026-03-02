# SAS Converter

A partition-based SAS-to-Python conversion pipeline using multi-agent architecture.

## Setup

```bash
# From repo root (Stage/)
python -m venv venv
.\venv\Scripts\Activate.ps1          # Windows

pip install -r sas_converter/requirements.txt
```

## Quick Start — CLI

```bash
# Process a single SAS file (full L2-A → L2-D pipeline)
python main.py --file path/to/your/file.sas

# Process an entire directory
python main.py --dir  path/to/sas/corpus/
```

## Quick Start — Demo

```bash
cd sas_converter
$env:PYTHONPATH    = "$PWD"
$env:LLM_PROVIDER = "none"          # deterministic only, no API key needed
$env:PYTHONIOENCODING = "utf-8"     # Windows: required for Unicode output
../venv/Scripts/python examples/demo_pipeline.py
```

Expected output: **4/4 blocks detected (100%)** on the bundled `examples/test_input.sas`.

## Project Structure

```
sas_converter/
├── partition/
│   ├── base_agent.py          # BaseAgent ABC
│   ├── logging_config.py      # structlog configuration
│   ├── models/                # Pydantic data models
│   ├── entry/                 # L2-A: FileAnalysis, CrossFileDeps, RegistryWriter, DataLineage
│   ├── streaming/             # L2-B: StreamAgent + StateAgent + pipeline
│   ├── chunking/              # L2-C: BoundaryDetector + PartitionBuilder + LLM resolver
│   ├── complexity/            # L2-D: ComplexityAgent (LogReg+Platt) + StrategyAgent
│   └── db/                    # SQLAlchemy database management
├── tests/                     # pytest test suite (73 tests)
├── benchmark/                 # 721-block accuracy benchmark
├── knowledge_base/
│   └── gold_standard/         # 50 annotated .sas + .gold.json files (3 complexity tiers)
├── docs/                      # PROJECT.md, API_REFERENCE, TECH_JUSTIFICATIONS, UML diagrams
├── config/
│   └── project_config.yaml    # Project configuration
├── examples/                  # Runnable end-to-end demos
│   ├── demo_pipeline.py       # Full L2 pipeline demo
│   └── test_input.sas         # Sample SAS file (4 blocks, 100% detection)
├── scripts/
│   └── debug/                 # Investigation scripts from benchmarking sessions (weeks 2–4)
│       └── output/            # Captured debug output (.txt)
├── logs/                      # Runtime logs
├── README.md

| Tier | Lines | Count | Description |
|------|-------|-------|-------------|
| **Simple** | 7–50 | ~15 | Single block type, minimal nesting |
| **Medium** | 100–250 | ~20 | Mixed block types, macro calls, realistic workflows |
| **Hard** | 400+ | ~15 | Enterprise-grade: multi-step ETL, nested macros, CALL EXECUTE, cross-file includes |

Each `.sas` file has a matching `.gold.json` annotation with block boundaries, partition types, and data lineage references.

## Data Lineage

Beyond file-level linking (`%INCLUDE`, `LIBNAME`), the system tracks **dataset-level data lineage**:

- **Table-level**: Which datasets each block reads from (`SET`, `MERGE`, `FROM`) and writes to (`DATA`, `CREATE TABLE`, `INSERT INTO`)
- **Column-level** (Phase 2): Which output columns derive from which input columns via which transformations
- **Cross-file data flow**: File A creates `work.temp` → File B reads `work.temp`

Lineage is stored in the `data_lineage` SQLite table and annotated in `.gold.json` files.

## Benchmark

| Metric | Value |
|--------|-------|
| Gold blocks | 721 (50 files, tolerance ±2 lines) |
| Target accuracy | **80%** |
| Current accuracy | **79.3%** (572/721) |

```bash
cd sas_converter
$env:PYTHONPATH = "$PWD"
../venv/Scripts/python benchmark/boundary_benchmark.py
```

## Running Tests

```bash
cd sas_converter
$env:PYTHONPATH = "$PWD"
../venv/Scripts/python -m pytest tests/ -v
