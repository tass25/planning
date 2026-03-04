# SAS-to-Python/PySpark Conversion Accelerator — Project Documentation

> **Version**: 0.1.0 (Week 1–2 milestone)  
> **Last updated**: 2026-02-20  
> **Repository**: [github.com/tass25/planning](https://github.com/tass25/planning)

---

## 1. Executive Summary

The **SAS-to-Python/PySpark Conversion Accelerator** is a multi-agent pipeline that automates the conversion of legacy SAS code into modern Python and PySpark equivalents. The system uses a 16-agent architecture organized in 6 layers, combining rule-based parsing with LLM-assisted translation and a RAPTOR-based knowledge base.

### Current State (Week 1–2 Complete)

| Metric | Value |
|--------|-------|
| Agents implemented | 4 / 16 |
| Gold standard corpus | 50 SAS files, 721 annotated blocks |
| Complexity tiers | 3 (simple, medium, hard) |
| Test suite | 20 tests, all passing |
| Database tables | 3 (file_registry, cross_file_deps, data_lineage) |

---

## 2. Architecture Overview

### 2.1 Layer Model

The pipeline is organized into **6 layers**:

| Layer | Name | Purpose | Agents |
|-------|------|---------|--------|
| **L2-A** | Entry & Scan | File discovery, encoding, hashing, cross-file deps, lineage | FileAnalysisAgent, CrossFileDependencyResolver, RegistryWriterAgent, DataLineageExtractor |
| **L2-B** | Streaming Core | Async chunked reading, FSM-based state tracking | StreamAgent, StateAgent |
| **L2-C** | RAPTOR Chunking | Boundary detection, partitioning, embedding, clustering, RAPTOR tree | BoundaryDetectorAgent, PartitionBuilderAgent, RAPTORPartitionAgent |
| **L2-D** | Complexity & Strategy | Risk scoring, strategy selection | ComplexityAgent, StrategyAgent |
| **L3** | Translation | SAS → Python/PySpark translation via LLM | TranslationAgent, ValidationAgent |
| **L4 + CL** | Merge & Learning | Output merging, reporting, continuous learning loop | ReportAgent, FeedbackIngestionAgent, ConversionQualityMonitor |

### 2.2 Data Flow

```
Raw .sas files
    │
    ▼
┌─────────────────────────────────┐
│  L2-A: Entry & Scan            │
│  FileAnalysisAgent ──►         │
│  CrossFileDependencyResolver ──►│
│  RegistryWriterAgent ──►       │
│  DataLineageExtractor ──►      │
│  SQLite DB (3 tables)          │
└─────────┬───────────────────────┘
          │
          ▼
┌─────────────────────────────────┐
│  L2-B: Streaming Core          │
│  StreamAgent → StateAgent      │
│  (async 8KB chunks, FSM)       │
└─────────┬───────────────────────┘
          │
          ▼
┌─────────────────────────────────┐
│  L2-C: RAPTOR Chunking         │
│  BoundaryDetector (Lark 80%    │
│  + LLM 20%) → PartitionBuilder│
│  → Embed → GMM → RAPTOR Tree  │
└─────────┬───────────────────────┘
          │
          ▼
┌─────────────────────────────────┐
│  L2-D: Complexity & Strategy   │
│  ComplexityAgent → StrategyAgent│
│  (sklearn LogReg, ECE < 0.08)  │
└─────────┬───────────────────────┘
          │
          ▼
┌─────────────────────────────────┐
│  L3: Translation               │
│  TranslationAgent (Groq/Ollama)│
│  → ValidationAgent (AST check) │
└─────────┬───────────────────────┘
          │
          ▼
┌─────────────────────────────────┐
│  L4 + CL: Merge & Learning     │
│  ReportAgent → Feedback →      │
│  ConversionQualityMonitor      │
└─────────────────────────────────┘
```

### 2.3 Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.10+ |
| Data models | Pydantic | ≥ 2.0 |
| Database | SQLAlchemy + SQLite (WAL) | ≥ 2.0 |
| Encoding detection | chardet | ≥ 5.0 |
| Parsing (future) | Lark (LALR) | ≥ 1.1 |
| Structured logging | structlog | ≥ 23.0 |
| Async I/O | aiofiles | ≥ 23.0 |
| Testing | pytest + pytest-cov | ≥ 7.0 |

---

## 3. Project Structure

```
sas_converter/
├── config/
│   └── project_config.yaml       # Central configuration
├── docs/
│   ├── PROJECT.md                # This file
│   ├── API_REFERENCE.md          # Module/class reference
│   ├── USER_GUIDE.md             # How-to guide
│   └── UML_DIAGRAMS.html         # Interactive UML diagrams
├── knowledge_base/
│   └── gold_standard/            # 50 annotated SAS files
│       ├── gs_*.sas / .gold.json     # 15 simple tier
│       ├── gsm_*.sas / .gold.json    # 20 medium tier
│       └── gsh_*.sas / .gold.json    # 15 hard tier
├── logs/
├── partition/
│   ├── __init__.py
│   ├── base_agent.py             # BaseAgent ABC + @with_retry
│   ├── logging_config.py         # structlog configuration
│   ├── models/
│   │   ├── enums.py              # PartitionType, RiskLevel, etc.
│   │   ├── file_metadata.py      # FileMetadata Pydantic model
│   │   └── partition_ir.py       # PartitionIR Pydantic model
│   ├── entry/
│   │   ├── file_analysis_agent.py
│   │   ├── cross_file_dep_resolver.py
│   │   ├── registry_writer_agent.py
│   │   └── data_lineage_extractor.py
│   └── db/
│       └── sqlite_manager.py     # ORM models + engine/session
├── tests/
│   ├── test_file_analysis.py     # 5 tests
│   ├── test_cross_file_deps.py   # 5 tests
│   ├── test_registry_writer.py   # 5 tests
│   └── test_data_lineage.py      # 5 tests
├── requirements.txt
└── README.md
```

---

## 4. Database Schema

The SQLite database uses **WAL journal mode** and **foreign key enforcement**.

### 4.1 `file_registry`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| file_id | STRING | PK | UUID of the file |
| file_path | STRING | NOT NULL | Path to .sas file |
| encoding | STRING | NOT NULL | Detected encoding (e.g. utf-8) |
| content_hash | STRING | NOT NULL, UNIQUE | SHA-256 hex digest |
| file_size_bytes | INTEGER | | File size |
| line_count | INTEGER | | Number of lines |
| lark_valid | BOOLEAN | | Pre-validation result |
| lark_errors | TEXT | | JSON list of errors |
| status | STRING | DEFAULT 'PENDING' | Processing status |
| error_log | TEXT | | Error details |
| created_at | STRING | NOT NULL | ISO timestamp |

### 4.2 `cross_file_deps`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Row ID |
| source_file_id | STRING | FK → file_registry | File containing the reference |
| ref_type | STRING | NOT NULL | INCLUDE or LIBNAME |
| raw_reference | STRING | NOT NULL | Original matched text |
| resolved | BOOLEAN | DEFAULT FALSE | Whether target was found |
| target_file_id | STRING | FK → file_registry, NULLABLE | Resolved target file |
| target_path | STRING | NULLABLE | Resolved absolute path |

### 4.3 `data_lineage`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PK, AUTO | Row ID |
| source_file_id | STRING | FK → file_registry | File containing the lineage |
| lineage_type | STRING | NOT NULL | TABLE_READ or TABLE_WRITE |
| source_dataset | STRING | NULLABLE | Dataset being read |
| target_dataset | STRING | NULLABLE | Dataset being written |
| source_columns | TEXT | NULLABLE | JSON list of columns (Phase 2) |
| target_column | STRING | NULLABLE | Computed column (Phase 2) |
| transform_expr | STRING | NULLABLE | Transform expression (Phase 2) |
| block_line_start | INTEGER | NULLABLE | Line number |
| block_line_end | INTEGER | NULLABLE | Line number |

---

## 5. Gold Standard Corpus

### 5.1 Tier Breakdown

| Tier | Prefix | Files | Block Count | Characteristics |
|------|--------|-------|-------------|-----------------|
| **Simple** | `gs_` | 15 | ~90 | Single block type, 7–50 lines, basic patterns |
| **Medium** | `gsm_` | 20 | ~340 | Mixed blocks, macros, realistic workflows, 100–250 lines |
| **Hard** | `gsh_` | 15 | ~291 | Enterprise ETL, nested macros, CALL EXECUTE, 400+ lines |
| **Total** | — | **50** | **721** | All 9 partition types covered |

### 5.2 Annotation Format (.gold.json)

```json
{
  "file": "gs_01_basic_data_step.sas",
  "tier": "simple",
  "expected_blocks": [
    {
      "type": "DATA_STEP",
      "line_start": 1,
      "line_end": 10,
      "datasets_read": ["raw.input"],
      "datasets_written": ["work.output"]
    }
  ],
  "data_lineage": {
    "reads": [{"dataset": "raw.input", "type": "SET"}],
    "writes": [{"dataset": "work.output", "type": "DATA"}]
  }
}
```

### 5.3 Partition Types (9)

| Type | SAS Construct | Example |
|------|---------------|---------|
| DATA_STEP | `DATA ... ; RUN;` | Data transformation |
| PROC_BLOCK | `PROC ... ; RUN/QUIT;` | Statistical procedures |
| MACRO_DEFINITION | `%MACRO ... %MEND` | Reusable macro |
| MACRO_INVOCATION | `%macro_name(...)` | Macro call |
| SQL_BLOCK | `PROC SQL; ... QUIT;` | SQL queries |
| CONDITIONAL_BLOCK | `%IF ... %THEN` | Conditional logic |
| LOOP_BLOCK | `%DO ... %END` | Looping constructs |
| GLOBAL_STATEMENT | `LIBNAME, FILENAME, OPTIONS` | Global declarations |
| INCLUDE_REFERENCE | `%INCLUDE '...'` | External file inclusion |

---

## 6. Configuration

See `config/project_config.yaml`:

```yaml
project:
  name: sas_converter
  version: "0.1.0"

paths:
  project_root: "."
  gold_standard: "knowledge_base/gold_standard"
  database: "file_registry.db"
  logs: "logs"

agents:
  file_analysis:
    encoding_fallback: "utf-8"
    hash_algorithm: "sha256"
  cross_file_deps:
    resolve_libname: true
    resolve_include: true
  registry_writer:
    dedup_on_hash: true
  data_lineage_extractor:
    phase: 1
    detect_reads: true
    detect_writes: true
```

---

## 7. Git & Branch Strategy

| Branch | Purpose | Contents |
|--------|---------|----------|
| `main` | Implementation code | sas_converter/ (source, tests, gold standard) |
| `Planning` | Planning & documentation | cahier des charges, week plans, architecture HTML, README |

**Commit convention**: `feat:`, `fix:`, `test:`, `docs:`, `chore:`

---

## 8. Roadmap

| Milestone | Weeks | Status |
|-----------|-------|--------|
| L2-A Entry & Scan | 1–2 | ✅ Complete |
| L2-B StreamAgent + StateAgent | 2–3 | 🔲 Next |
| L2-C BoundaryDetector + LLM | 3–4 | 🔲 Planned |
| L2-D Complexity + Strategy | 4 | 🔲 Planned |
| L2-C RAPTOR (Nomic + GMM) | 5–6 | 🔲 Planned |
| Persistence + Kuzu | 7 | 🔲 Planned |
| Orchestration + Redis | 8 | 🔲 Planned |
| Robustness + KB gen | 9 | 🔲 Planned |
| L3 Translation + Validation | 10 | 🔲 Planned |
| L4 + CL Merge + Learning | 11 | 🔲 Planned |
| Ablation study | 12 | 🔲 Planned |
| Defense prep | 13–14 | 🔲 Planned |
