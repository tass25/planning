# User Guide — SAS-to-Python/PySpark Conversion Accelerator

> **Version**: 0.1.0 (Week 1–2)  
> **Last updated**: 2026-02-20

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installation](#2-installation)
3. [Quick Start](#3-quick-start)
4. [Using the Agents](#4-using-the-agents)
5. [Working with the Database](#5-working-with-the-database)
6. [Gold Standard Corpus](#6-gold-standard-corpus)
7. [Running Tests](#7-running-tests)
8. [Configuration](#8-configuration)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Prerequisites

| Requirement | Minimum Version |
|-------------|----------------|
| Python | 3.10+ |
| pip | 21.0+ |
| Git | 2.30+ |
| Operating System | Windows 10+, macOS 12+, Linux |

---

## 2. Installation

### 2.1 Clone the repository

```bash
git clone https://github.com/tass25/planning.git
cd planning
```

### 2.2 Create a virtual environment

**Windows:**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2.3 Install dependencies

```bash
cd sas_converter
pip install -r requirements.txt
```

This installs:
- `pydantic` — Data validation models
- `sqlalchemy` — Database ORM
- `chardet` — Encoding detection
- `lark` — Parser toolkit (used in later weeks)
- `structlog` — Structured logging
- `aiofiles` — Async file I/O
- `pytest` + `pytest-cov` — Testing

---

## 3. Quick Start

### 3.1 Scan SAS files

```python
import asyncio
from pathlib import Path
from sas_converter.partition.entry.file_analysis_agent import FileAnalysisAgent

async def main():
    agent = FileAnalysisAgent()
    
    # Point to a directory containing .sas files
    project_root = Path("knowledge_base/gold_standard")
    
    # Scan all .sas files
    results = await agent.process(project_root)
    
    for meta in results:
        print(f"{meta.file_path}")
        print(f"  Encoding: {meta.encoding}")
        print(f"  Lines:    {meta.line_count}")
        print(f"  SHA-256:  {meta.content_hash[:16]}...")
        print(f"  Valid:    {meta.lark_valid}")
        print()

asyncio.run(main())
```

### 3.2 Full pipeline (scan → register → resolve deps → extract lineage)

```python
import asyncio
from pathlib import Path

from sas_converter.partition.entry.file_analysis_agent import FileAnalysisAgent
from sas_converter.partition.entry.registry_writer_agent import RegistryWriterAgent
from sas_converter.partition.entry.cross_file_dep_resolver import CrossFileDependencyResolver
from sas_converter.partition.entry.data_lineage_extractor import DataLineageExtractor
from sas_converter.partition.db.sqlite_manager import get_engine, init_db

async def run_pipeline():
    # 1. Initialize database
    engine = get_engine("file_registry.db")
    init_db(engine)
    
    project_root = Path("knowledge_base/gold_standard")
    
    # 2. Scan files
    scanner = FileAnalysisAgent()
    files = await scanner.process(project_root)
    print(f"Scanned {len(files)} SAS files")
    
    # 3. Write to registry
    writer = RegistryWriterAgent()
    result = await writer.process(files, engine)
    print(f"Inserted: {result['inserted']}, Skipped: {result['skipped']}")
    
    # 4. Resolve cross-file dependencies
    resolver = CrossFileDependencyResolver()
    deps = await resolver.process(files, project_root, engine)
    print(f"Dependencies: {deps['total']} (resolved: {deps['resolved']})")
    
    # 5. Extract data lineage
    lineage = DataLineageExtractor()
    lin = await lineage.process(files, engine)
    print(f"Lineage: {lin['total_reads']} reads, {lin['total_writes']} writes")

asyncio.run(run_pipeline())
```

---

## 4. Using the Agents

### 4.1 FileAnalysisAgent

**Purpose**: Discover and scan `.sas` files in a directory.

```python
from sas_converter.partition.entry.file_analysis_agent import FileAnalysisAgent

agent = FileAnalysisAgent()
# Optional: provide a trace_id for correlation
# agent = FileAnalysisAgent(trace_id=my_uuid)

results = await agent.process(Path("/path/to/sas/files"))
```

**Output**: List of `FileMetadata` objects with encoding, hash, line count, and validation status.

### 4.2 RegistryWriterAgent

**Purpose**: Persist file metadata to the SQLite database with deduplication.

```python
from sas_converter.partition.entry.registry_writer_agent import RegistryWriterAgent
from sas_converter.partition.db.sqlite_manager import get_engine, init_db

engine = get_engine("my_database.db")
init_db(engine)

writer = RegistryWriterAgent()
result = await writer.process(files, engine)
# result = {"inserted": 50, "skipped": 0}
```

**Deduplication**: Files with the same SHA-256 hash are automatically skipped.

### 4.3 CrossFileDependencyResolver

**Purpose**: Find `%INCLUDE` and `LIBNAME` references between SAS files.

```python
from sas_converter.partition.entry.cross_file_dep_resolver import CrossFileDependencyResolver

resolver = CrossFileDependencyResolver()
deps = await resolver.process(files, project_root, engine)
# deps = {"total": 12, "resolved": 8, "unresolved": 4}
```

**Resolution logic**:
1. Tries path relative to the source file's directory
2. Tries path relative to the project root
3. `%INCLUDE &macro_var` — marked as unresolvable (dynamic reference)

### 4.4 DataLineageExtractor

**Purpose**: Extract table-level data lineage (what datasets are read / written).

```python
from sas_converter.partition.entry.data_lineage_extractor import DataLineageExtractor

extractor = DataLineageExtractor()
lineage = await extractor.process(files, engine)
# lineage = {"total_reads": 85, "total_writes": 42, "total": 127}
```

**What it detects**:
- **Reads**: `SET`, `MERGE`, `FROM`, `JOIN` statements
- **Writes**: `DATA output`, `CREATE TABLE`, `INSERT INTO` statements

---

## 5. Working with the Database

### 5.1 Create / connect to a database

```python
from sas_converter.partition.db.sqlite_manager import get_engine, init_db, get_session

# Create engine (applies WAL mode + FK enforcement)
engine = get_engine("file_registry.db")

# Create tables if they don't exist
init_db(engine)

# Get a session for queries
session = get_session(engine)
```

### 5.2 Query the file registry

```python
from sas_converter.partition.db.sqlite_manager import FileRegistryRow

session = get_session(engine)

# List all files
all_files = session.query(FileRegistryRow).all()
for f in all_files:
    print(f"{f.file_path} — {f.encoding} — {f.status}")

# Find invalid files
invalid = session.query(FileRegistryRow).filter_by(lark_valid=False).all()
```

### 5.3 Query cross-file dependencies

```python
from sas_converter.partition.db.sqlite_manager import CrossFileDependencyRow

# All unresolved dependencies
unresolved = session.query(CrossFileDependencyRow).filter_by(resolved=False).all()
for dep in unresolved:
    print(f"{dep.ref_type}: {dep.raw_reference}")
```

### 5.4 Query data lineage

```python
from sas_converter.partition.db.sqlite_manager import DataLineageRow

# All dataset reads
reads = session.query(DataLineageRow).filter_by(lineage_type="TABLE_READ").all()
for r in reads:
    print(f"Read: {r.source_dataset} (line {r.block_line_start})")

# All dataset writes
writes = session.query(DataLineageRow).filter_by(lineage_type="TABLE_WRITE").all()
for w in writes:
    print(f"Write: {w.target_dataset} (line {w.block_line_start})")
```

---

## 6. Gold Standard Corpus

### 6.1 Location

```
sas_converter/knowledge_base/gold_standard/
```

### 6.2 File naming convention

| Prefix | Tier | Files | Lines per file |
|--------|------|-------|----------------|
| `gs_` | Simple | 15 | 7–50 |
| `gsm_` | Medium | 20 | 100–250 |
| `gsh_` | Hard | 15 | 400+ |

Each `.sas` file has a matching `.gold.json` annotation file.

### 6.3 Using gold standard for validation

```python
import json
from pathlib import Path

gold_dir = Path("knowledge_base/gold_standard")

for gold_json in sorted(gold_dir.glob("*.gold.json")):
    with open(gold_json) as f:
        annotation = json.load(f)
    
    print(f"{annotation['file']} — Tier: {annotation['tier']}")
    print(f"  Blocks: {len(annotation['expected_blocks'])}")
    
    for block in annotation["expected_blocks"]:
        print(f"    {block['type']} (lines {block['line_start']}–{block['line_end']})")
```

### 6.4 Adding new gold standard files

1. Create a `.sas` file with realistic SAS code in `knowledge_base/gold_standard/`
2. Create a matching `.gold.json` with block annotations
3. Make sure the JSON includes:
   - `file`: filename
   - `tier`: `"simple"`, `"medium"`, or `"hard"`
   - `expected_blocks`: array of block annotations with `type`, `line_start`, `line_end`
   - `data_lineage`: optional reads/writes

---

## 7. Running Tests

### 7.1 Run all tests

```bash
cd sas_converter
python -m pytest tests/ -v
```

Expected output:
```
tests/test_file_analysis.py::test_...    PASSED
tests/test_cross_file_deps.py::test_...  PASSED
tests/test_registry_writer.py::test_...  PASSED
tests/test_data_lineage.py::test_...     PASSED
==================== 20 passed ====================
```

### 7.2 Run with coverage

```bash
python -m pytest tests/ -v --cov=partition --cov-report=term-missing
```

### 7.3 Run a specific test file

```bash
python -m pytest tests/test_file_analysis.py -v
```

### 7.4 Run a specific test

```bash
python -m pytest tests/test_file_analysis.py::test_discovery_finds_sas_files -v
```

---

## 8. Configuration

### 8.1 Project config

Edit `config/project_config.yaml`:

```yaml
project:
  name: sas_converter
  version: "0.1.0"

paths:
  project_root: "."
  gold_standard: "knowledge_base/gold_standard"
  database: "file_registry.db"
  logs: "logs"

logging:
  level: INFO
  format: console    # 'console' for dev, 'json' for production

agents:
  data_lineage_extractor:
    phase: 1          # 1 = table-level regex, 2 = column-level (Lark)
    detect_reads: true
    detect_writes: true
```

### 8.2 Logging modes

**Development** (colored console output):
```python
from sas_converter.partition.logging_config import configure_logging
configure_logging()
```

**Production** (JSON to file):
```python
configure_logging(log_file="logs/pipeline.log", json_output=True)
```

---

## 9. Troubleshooting

### "ModuleNotFoundError: No module named 'sas_converter'"

Make sure you run from the project root (one level above `sas_converter/`):
```bash
cd Stage  # Not cd Stage/sas_converter
python -m pytest sas_converter/tests/ -v
```

Or add the project root to `PYTHONPATH`:
```bash
set PYTHONPATH=.
python -m pytest sas_converter/tests/ -v
```

### "PRAGMA foreign_keys=ON not working"

SQLite foreign key enforcement is set per-connection. The `get_engine()` function handles this automatically via an event listener. Don't create engines manually — always use `get_engine()`.

### "chardet returns None encoding"

The `FileAnalysisAgent` falls back to `"utf-8"` when chardet returns None. If you encounter files with unusual encodings, check the `encoding_fallback` setting in `project_config.yaml`.

### "Pre-validation reports false positives"

The current pre-validator uses regex heuristics (not a full Lark grammar). It may flag valid SAS code with unconventional structure. A full Lark LALR parser is planned for Week 3–4.

### Database locked errors

The SQLite engine uses WAL (Write-Ahead Logging) mode for better concurrency. If you still see locking issues, ensure you're:
1. Using `get_session()` and closing sessions properly
2. Not running multiple writers simultaneously
3. Not keeping sessions open longer than necessary
