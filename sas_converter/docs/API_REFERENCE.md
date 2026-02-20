# API Reference — SAS Converter

> **Version**: 0.1.0 (Week 1–2)  
> **Last updated**: 2026-02-20

---

## Table of Contents

1. [partition.base_agent](#1-partitionbase_agent)
2. [partition.logging_config](#2-partitionlogging_config)
3. [partition.models.enums](#3-partitionmodelsenums)
4. [partition.models.file_metadata](#4-partitionmodelsfile_metadata)
5. [partition.models.partition_ir](#5-partitionmodelspartition_ir)
6. [partition.db.sqlite_manager](#6-partitiondbsqlite_manager)
7. [partition.entry.file_analysis_agent](#7-partitionentryfile_analysis_agent)
8. [partition.entry.cross_file_dep_resolver](#8-partitionentrycross_file_dep_resolver)
9. [partition.entry.registry_writer_agent](#9-partitionentryregistry_writer_agent)
10. [partition.entry.data_lineage_extractor](#10-partitionentrydata_lineage_extractor)

---

## 1. `partition.base_agent`

**File**: `partition/base_agent.py`

### `with_retry(max_retries=3, base_delay=1.0, fallback=None)`

Decorator for async methods with exponential backoff retry logic.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_retries` | `int` | 3 | Maximum retry attempts |
| `base_delay` | `float` | 1.0 | Base delay in seconds (doubled each attempt) |
| `fallback` | `callable` | None | Optional callable returning a fallback value on exhaustion |

**Backoff formula**: `delay = base_delay × 2^attempt`

**Usage**:
```python
class MyAgent(BaseAgent):
    @with_retry(max_retries=5, base_delay=0.5)
    async def process(self, data):
        ...
```

---

### `class BaseAgent(ABC)`

Abstract base class for all pipeline agents.

**Constructor**:
```python
BaseAgent(trace_id: UUID | None = None)
```

| Attribute | Type | Description |
|-----------|------|-------------|
| `trace_id` | `UUID` | Auto-generated if not supplied |
| `logger` | `structlog.BoundLogger` | Bound with `agent` name and `trace_id` |

**Abstract properties**:

| Property | Returns | Description |
|----------|---------|-------------|
| `agent_name` | `str` | Human-readable name for logging |

**Abstract methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `process()` | `async process(*args, **kwargs)` | Main logic (must be overridden) |

---

## 2. `partition.logging_config`

**File**: `partition/logging_config.py`

### `configure_logging(log_file=None, json_output=False)`

Configure structlog for the project.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `log_file` | `str \| None` | None | Path to log file (stdout only if None) |
| `json_output` | `bool` | False | JSONRenderer (prod) vs ConsoleRenderer (dev) |

**Processors configured**:
- `merge_contextvars` — Thread-local context
- `add_log_level` — INFO/WARNING/ERROR
- `TimeStamper(fmt="iso")` — ISO-8601 timestamps
- `StackInfoRenderer` — Stack traces
- `format_exc_info` — Exception formatting

---

## 3. `partition.models.enums`

**File**: `partition/models/enums.py`

### `class PartitionType(str, Enum)`

The 9 SAS block types recognized by the partitioner.

| Value | SAS Construct |
|-------|---------------|
| `DATA_STEP` | `DATA ... ; ... RUN;` |
| `PROC_BLOCK` | `PROC ... ; ... RUN;` or `QUIT;` |
| `MACRO_DEFINITION` | `%MACRO ... %MEND` |
| `MACRO_INVOCATION` | `%macro_name(args)` |
| `SQL_BLOCK` | `PROC SQL; ... QUIT;` |
| `CONDITIONAL_BLOCK` | `%IF ... %THEN ... %ELSE` |
| `LOOP_BLOCK` | `%DO ... %END` |
| `GLOBAL_STATEMENT` | `LIBNAME`, `FILENAME`, `OPTIONS` |
| `INCLUDE_REFERENCE` | `%INCLUDE 'path'` |

### `class RiskLevel(str, Enum)`

| Value | Meaning |
|-------|---------|
| `LOW` | Simple, direct translation |
| `MODERATE` | Requires some adaptation |
| `HIGH` | Complex, needs human review |
| `UNCERTAIN` | Not yet assessed |

### `class ConversionStatus(str, Enum)`

| Value | Meaning |
|-------|---------|
| `SUCCESS` | Fully converted |
| `PARTIAL` | Partially converted |
| `FAILED` | Conversion failed |
| `HUMAN_REVIEW` | Requires manual review |

### `class PartitionStrategy(str, Enum)`

| Value | Description |
|-------|-------------|
| `FLAT_PARTITION` | Simple sequential split |
| `MACRO_AWARE` | Respects macro boundaries |
| `DEPENDENCY_PRESERVING` | Maintains data dependencies |
| `STRUCTURAL_GROUPING` | Groups related blocks |
| `HUMAN_REVIEW` | Too complex for automation |

---

## 4. `partition.models.file_metadata`

**File**: `partition/models/file_metadata.py`

### `class FileMetadata(BaseModel)`

Pydantic model produced by `FileAnalysisAgent`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `file_id` | `UUID` | `uuid4()` | Unique identifier |
| `file_path` | `str` | *required* | Path to the .sas file |
| `encoding` | `str` | *required* | Detected encoding (e.g. `utf-8`) |
| `content_hash` | `str` | *required* | SHA-256 hex digest |
| `file_size_bytes` | `int` | *required* | File size in bytes |
| `line_count` | `int` | *required* | Number of lines |
| `lark_valid` | `bool` | *required* | Pre-validation result |
| `lark_errors` | `list[str]` | `[]` | Error messages |
| `created_at` | `datetime` | `now(UTC)` | Timestamp |

---

## 5. `partition.models.partition_ir`

**File**: `partition/models/partition_ir.py`

### `class PartitionIR(BaseModel)`

Intermediate representation of one SAS code block. This is the core unit flowing through the pipeline.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `block_id` | `UUID` | `uuid4()` | Unique block identifier |
| `file_id` | `UUID` | *required* | Parent FileMetadata reference |
| `partition_type` | `PartitionType` | *required* | One of the 9 block types |
| `source_code` | `str` | *required* | Raw SAS source code |
| `line_start` | `int` | *required* | 1-based start line |
| `line_end` | `int` | *required* | 1-based end line |
| `risk_level` | `RiskLevel` | `UNCERTAIN` | Assessed conversion difficulty |
| `conversion_status` | `ConversionStatus` | `HUMAN_REVIEW` | Pipeline status |
| `dependencies` | `list[UUID]` | `[]` | Block IDs this block depends on |
| `metadata` | `dict[str, Any]` | `{}` | Arbitrary key/value for downstream |
| `created_at` | `datetime` | `now(UTC)` | Timestamp |

---

## 6. `partition.db.sqlite_manager`

**File**: `partition/db/sqlite_manager.py`

### ORM Models

#### `class FileRegistryRow(Base)`

Table name: `file_registry`

| Column | SQLAlchemy Type | Constraints |
|--------|----------------|-------------|
| `file_id` | `String` | PK |
| `file_path` | `String` | NOT NULL |
| `encoding` | `String` | NOT NULL |
| `content_hash` | `String` | NOT NULL, UNIQUE |
| `file_size_bytes` | `Integer` | — |
| `line_count` | `Integer` | — |
| `lark_valid` | `Boolean` | — |
| `lark_errors` | `Text` | DEFAULT `""` |
| `status` | `String` | DEFAULT `"PENDING"` |
| `error_log` | `Text` | DEFAULT `""` |
| `created_at` | `String` | NOT NULL |

#### `class CrossFileDependencyRow(Base)`

Table name: `cross_file_deps`

| Column | SQLAlchemy Type | Constraints |
|--------|----------------|-------------|
| `id` | `Integer` | PK, AUTO |
| `source_file_id` | `String` | FK → `file_registry.file_id` |
| `ref_type` | `String` | NOT NULL |
| `raw_reference` | `String` | NOT NULL |
| `resolved` | `Boolean` | DEFAULT FALSE |
| `target_file_id` | `String` | FK → `file_registry.file_id`, NULLABLE |
| `target_path` | `String` | NULLABLE |

#### `class DataLineageRow(Base)`

Table name: `data_lineage`

| Column | SQLAlchemy Type | Constraints |
|--------|----------------|-------------|
| `id` | `Integer` | PK, AUTO |
| `source_file_id` | `String` | FK → `file_registry.file_id` |
| `lineage_type` | `String` | NOT NULL (`TABLE_READ` / `TABLE_WRITE`) |
| `source_dataset` | `String` | NULLABLE |
| `target_dataset` | `String` | NULLABLE |
| `source_columns` | `Text` | NULLABLE (future: JSON list) |
| `target_column` | `String` | NULLABLE (future) |
| `transform_expr` | `String` | NULLABLE (future) |
| `block_line_start` | `Integer` | NULLABLE |
| `block_line_end` | `Integer` | NULLABLE |

### Functions

#### `get_engine(db_path="file_registry.db") → Engine`

Create a SQLAlchemy engine with SQLite WAL mode and foreign key enforcement.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | `str` | `"file_registry.db"` | Path to the SQLite database file |

**PRAGMA statements applied on every connection**:
- `PRAGMA journal_mode=WAL`
- `PRAGMA foreign_keys=ON`

#### `init_db(engine) → None`

Create all tables that don't already exist (idempotent).

#### `get_session(engine) → Session`

Return a new SQLAlchemy Session bound to the given engine.

---

## 7. `partition.entry.file_analysis_agent`

**File**: `partition/entry/file_analysis_agent.py`

### `class FileAnalysisAgent(BaseAgent)`

**Agent name**: `"FileAnalysisAgent"`

Scans a project directory recursively for `.sas` files and produces `FileMetadata` objects.

#### `async process(project_root: Path) → list[FileMetadata]`

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_root` | `Path` | Directory to scan recursively |

**Returns**: List of `FileMetadata` objects, one per `.sas` file found.

**Processing steps**:
1. Discover all `*.sas` files via `rglob("*.sas")`
2. For each file:
   - Detect encoding with `chardet.detect()`
   - Decode content (with `errors="replace"`)
   - Compute SHA-256 hash on raw bytes
   - Count lines
   - Run pre-validation (balanced block check)
3. Log summary: total, valid, invalid counts

### Pre-validation (private)

The `_pre_validate(content)` function checks:
- **Block balance**: `DATA/PROC` openers ≤ `RUN/QUIT` closers
- **Macro balance**: `%MACRO` count = `%MEND` count
- Comments are stripped before checking (`/* ... */` and `* ... ;`)

---

## 8. `partition.entry.cross_file_dep_resolver`

**File**: `partition/entry/cross_file_dep_resolver.py`

### `class CrossFileDependencyResolver(BaseAgent)`

**Agent name**: `"CrossFileDependencyResolver"`

Scans SAS content for cross-file references and persists them to the database.

#### `async process(files, project_root, engine) → dict`

| Parameter | Type | Description |
|-----------|------|-------------|
| `files` | `list[FileMetadata]` | Files to scan |
| `project_root` | `Path` | Base directory for resolution |
| `engine` | `Engine` | SQLAlchemy engine |

**Returns**: `{"total": int, "resolved": int, "unresolved": int}`

**Regex patterns used**:

| Pattern | Matches | ref_type |
|---------|---------|----------|
| `INCLUDE_PATTERN` | `%INCLUDE 'path'` | INCLUDE |
| `LIBNAME_PATTERN` | `LIBNAME name 'path'` | LIBNAME |
| `MACRO_VAR_INCLUDE` | `%INCLUDE &var` | INCLUDE (unresolvable) |

**Resolution strategy** (for `%INCLUDE`):
1. Try relative to the source file's directory
2. Try relative to the project root
3. If neither matches → `resolved=False`

---

## 9. `partition.entry.registry_writer_agent`

**File**: `partition/entry/registry_writer_agent.py`

### `class RegistryWriterAgent(BaseAgent)`

**Agent name**: `"RegistryWriterAgent"`

Writes `FileMetadata` records into the `file_registry` SQLite table with content-hash deduplication.

#### `async process(files, engine) → dict`

| Parameter | Type | Description |
|-----------|------|-------------|
| `files` | `list[FileMetadata]` | Files to persist |
| `engine` | `Engine` | SQLAlchemy engine |

**Returns**: `{"inserted": int, "skipped": int}`

**Deduplication**: Checks `content_hash` before inserting — files with the same SHA-256 hash are skipped.

---

## 10. `partition.entry.data_lineage_extractor`

**File**: `partition/entry/data_lineage_extractor.py`

### `class DataLineageExtractor(BaseAgent)`

**Agent name**: `"DataLineageExtractor"`

Scans SAS content for table-level data lineage (reads and writes) and persists edges to the `data_lineage` table.

#### `async process(files, engine) → dict`

| Parameter | Type | Description |
|-----------|------|-------------|
| `files` | `list[FileMetadata]` | Files to scan |
| `engine` | `Engine` | SQLAlchemy engine |

**Returns**: `{"total_reads": int, "total_writes": int, "total": int}`

**Detected patterns**:

| Category | Pattern | SAS Construct | Example |
|----------|---------|---------------|---------|
| TABLE_READ | `SET_PATTERN` | `SET dataset;` | `SET lib.input;` |
| TABLE_READ | `MERGE_PATTERN` | `MERGE ds1 ds2;` | `MERGE a b;` |
| TABLE_READ | `FROM_PATTERN` | `FROM table` | `FROM sales` |
| TABLE_READ | `JOIN_PATTERN` | `JOIN table` | `LEFT JOIN customers` |
| TABLE_WRITE | `DATA_OUTPUT_PATTERN` | `DATA dataset;` | `DATA out.summary;` |
| TABLE_WRITE | `CREATE_TABLE_PATTERN` | `CREATE TABLE t` | `CREATE TABLE report` |
| TABLE_WRITE | `INSERT_INTO_PATTERN` | `INSERT INTO t` | `INSERT INTO staging` |

**Helper functions**:

| Function | Purpose |
|----------|---------|
| `_split_datasets(raw)` | Tokenize dataset list, strip options `(WHERE=...)`, filter `_NULL_` |
| `_line_of(content, pos)` | Convert char position to 1-based line number |

**Ignored tokens**: `_null_`, `_data_`, `_last_`, `_infile_`, and any token starting with `_`.

---

## Test Coverage

| Test File | Tests | Agent Tested |
|-----------|-------|-------------|
| `test_file_analysis.py` | 5 | FileAnalysisAgent |
| `test_cross_file_deps.py` | 5 | CrossFileDependencyResolver |
| `test_registry_writer.py` | 5 | RegistryWriterAgent |
| `test_data_lineage.py` | 5 | DataLineageExtractor |
| **Total** | **20** | All passing (2026-02-20) |
