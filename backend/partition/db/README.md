# Database Layer

SQLite (relational) + DuckDB (analytics) dual-database architecture.

## Files

| File | Description |
|------|-------------|
| `sqlite_manager.py` | SQLAlchemy ORM — 6 tables, WAL journal mode, foreign keys PRAGMA |
| `duckdb_manager.py` | DuckDB analytics — 7 tables for audit, calibration, ablation, quality metrics |

## SQLite Tables (via SQLAlchemy ORM)

| Table | ORM Class | Purpose |
|-------|-----------|---------|
| `file_registry` | `FileRegistryRow` | File metadata (path, encoding, hash, size, line count) |
| `cross_file_deps` | `CrossFileDependencyRow` | `%INCLUDE` / `LIBNAME` / `&macro` references |
| `data_lineage` | `DataLineageRow` | Dataset-level read/write lineage per block |
| `partition_ir` | `PartitionIRRow` | Partition blocks with risk, strategy, RAPTOR back-links |
| `conversion_results` | `ConversionResultRow` | Conversion output (future) |
| `merged_scripts` | `MergedScriptRow` | Merged multi-file scripts (future) |

## DuckDB Tables

| Table | Purpose |
|-------|---------|
| `llm_audit` | Every LLM call: model, latency, token count, prompt/response hashes |
| `calibration_log` | Platt scaling calibration history (ECE, Brier, reliability) |
| `ablation_results` | Feature ablation study results |
| `quality_metrics` | Per-file quality scores |
| `feedback_log` | Human feedback on conversions |
| `kb_changelog` | Knowledge base change tracking |
| `conversion_reports` | Full conversion report data |

## Configuration

- SQLite: WAL journal mode, foreign keys enabled via PRAGMA
- DuckDB: File-based (`analytics.duckdb`), auto-created tables

## Dependencies

`sqlalchemy` (ORM, create_engine, event, declarative_base), `duckdb`
