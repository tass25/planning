# SAS Converter — Progress Checklist

## Week 1–2: L2-A — Entry & Scan + Gold Standard Corpus

### Infrastructure
- [x] `.gitignore` created
- [x] `checklist.md` created
- [x] Project scaffold (directory structure + `__init__.py` files)
- [x] `requirements.txt` created
- [x] Dependencies installed in venv

### Core Code
- [x] `partition/base_agent.py` — BaseAgent ABC with `@with_retry` decorator
- [x] `partition/logging_config.py` — structlog configuration
- [x] `partition/models/enums.py` — PartitionType, RiskLevel, ConversionStatus, PartitionStrategy
- [x] `partition/models/file_metadata.py` — FileMetadata Pydantic model
- [x] `partition/models/partition_ir.py` — PartitionIR Pydantic model
- [x] `partition/db/sqlite_manager.py` — SQLAlchemy engine + session factory + WAL mode
- [x] `partition/entry/file_analysis_agent.py` — FileAnalysisAgent with regex pre-validation
- [x] `partition/entry/cross_file_dep_resolver.py` — CrossFileDependencyResolver (3 regex patterns)
- [x] `partition/entry/registry_writer_agent.py` — RegistryWriterAgent with INSERT OR IGNORE dedup

### Tests
- [x] `tests/test_file_analysis.py` — 5 tests passing
- [x] `tests/test_cross_file_deps.py` — 5 tests passing
- [x] `tests/test_registry_writer.py` — 5 tests passing
- [x] All tests pass: `pytest tests/ -v` → **15 passed** (2026-02-19)

### Gold Standard Corpus (3 Complexity Tiers)
- [x] 50 `.sas` files created in `knowledge_base/gold_standard/`
- [x] 50 `.gold.json` annotation files created
- [x] ~15 simple files (7–50 lines) — `gs_*` prefix, single block type
- [x] ~20 medium files (100–250 lines) — `gsm_*` prefix, mixed blocks, macros, realistic workflows
- [x] ~15 hard files (400+ lines) — `gsh_*` prefix, enterprise ETL, nested macros, CALL EXECUTE
- [x] 721 total blocks annotated across all tiers
- [x] `.gold.json` extended with `data_lineage` annotations

### Data Lineage Tracking
- [x] `DataLineageRow` model added to `sqlite_manager.py`
- [x] `data_lineage` table auto-created via `init_db()`
- [x] `data_lineage_extractor.py` — regex extraction (SET, MERGE, FROM, JOIN, DATA, CREATE TABLE, INSERT INTO)
- [x] `tests/test_data_lineage.py` — 5 tests passing
- [x] Gold standard `.gold.json` annotated with `data_lineage` fields

### Database
- [x] `file_registry` table schema created (SQLAlchemy ORM)
- [x] `cross_file_deps` table schema created (SQLAlchemy ORM)
- [x] `data_lineage` table schema created (SQLAlchemy ORM)

### Git
- [ ] Pushed to `main` in batches of ~4 files

---

## Problems Encountered
1. **Windows `\r\n` vs `\n`**: `write_text` on Windows uses `\r\n`, causing SHA-256 hash mismatch in tests. Fixed by hashing from `read_bytes()`.
2. **Cross-file dep resolution test**: Target file must be in the `files` list for the resolver to build a file index. Fixed by passing both source and target.
3. **chardet Latin-1 detection**: `chardet` may report `ISO-8859-1` or `Windows-1252` — tests accept both.

---

## Notes
- Using existing `venv/` virtual environment
- Lark grammar is pre-validation only (balanced block check) — full grammar comes in Week 3–4
- SHA-256 computed on raw bytes before decoding for encoding-independent dedup
