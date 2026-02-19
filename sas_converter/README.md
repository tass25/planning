# SAS Converter

A partition-based SAS-to-Python conversion pipeline using multi-agent architecture.

## Setup

```bash
# Activate virtual environment
.\venv\Scripts\Activate.ps1  # Windows

# Install dependencies
pip install -r sas_converter/requirements.txt
```

## Project Structure

```
sas_converter/
├── partition/
│   ├── base_agent.py          # BaseAgent ABC
│   ├── logging_config.py      # structlog configuration
│   ├── models/                # Pydantic data models
│   ├── entry/                 # L2-A agents (FileAnalysis, CrossFileDeps, RegistryWriter, DataLineageExtractor)
│   └── db/                    # SQLAlchemy database management
├── tests/                     # pytest test suite
├── knowledge_base/
│   └── gold_standard/         # 50 annotated .sas + .gold.json files (3 complexity tiers)
├── config/
│   └── project_config.yaml    # Project configuration
└── requirements.txt
```

## Gold Standard Corpus

The gold standard corpus contains 50 annotated SAS files across **3 complexity tiers**:

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

## Running Tests

```bash
pytest sas_converter/tests/ -v --cov=sas_converter.partition
```
