# SAS Converter — Progress Checklist

## Week 1–2: L2-A — Entry & Scan + Gold Standard Corpus

### Infrastructure
- [x] `.gitignore` created
- [x] `checklist.md` created
- [ ] Project scaffold (directory structure + `__init__.py` files)
- [ ] `requirements.txt` created
- [ ] Dependencies installed in venv

### Core Code
- [ ] `partition/base_agent.py` — BaseAgent ABC with `@with_retry` decorator
- [ ] `partition/logging_config.py` — structlog configuration
- [ ] `partition/models/enums.py` — PartitionType, RiskLevel, ConversionStatus, PartitionStrategy
- [ ] `partition/models/file_metadata.py` — FileMetadata Pydantic model
- [ ] `partition/models/partition_ir.py` — PartitionIR Pydantic model
- [ ] `partition/db/sqlite_manager.py` — SQLAlchemy engine + session factory + WAL mode
- [ ] `partition/entry/file_analysis_agent.py` — FileAnalysisAgent with Lark pre-validation
- [ ] `partition/entry/cross_file_dep_resolver.py` — CrossFileDependencyResolver (3 regex patterns)
- [ ] `partition/entry/registry_writer_agent.py` — RegistryWriterAgent with INSERT OR IGNORE dedup

### Tests
- [ ] `tests/test_file_analysis.py` — 5 tests passing
- [ ] `tests/test_cross_file_deps.py` — 5 tests passing
- [ ] `tests/test_registry_writer.py` — 5 tests passing
- [ ] All tests pass: `pytest tests/ -v --cov=partition`

### Gold Standard Corpus
- [ ] 50 `.sas` files created in `knowledge_base/gold_standard/`
- [ ] 50 `.gold.json` annotation files created
- [ ] ~150 blocks annotated across all files
- [ ] Target distribution met (DATA_STEP: 40, PROC_BLOCK: 30, etc.)

### Database
- [ ] `file_registry` table created and populated
- [ ] `cross_file_deps` table created and populated

### Git
- [ ] Pushed to `main` in batches of ~4 files

---

## Problems Encountered
_None yet._

---

## Notes
- Using existing `venv/` virtual environment
- Lark grammar is pre-validation only (balanced block check) — full grammar comes in Week 3–4
- SHA-256 computed on raw bytes before decoding for encoding-independent dedup
