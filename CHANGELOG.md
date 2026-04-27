# Changelog

All notable changes to Codara are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [3.1.0] — 2026-04-12

### Added
- `backend/api/services/` layer: `ConversionService`, `PipelineService`, `TranslationService`
  extracted from the 1063-line `routes/conversions.py` god file
- `backend/config/constants.py` — named constants replacing magic numbers
  (`AZURE_MAX_COMPLETION_TOKENS`, `GROQ_MAX_TOKENS`, `SSE_MAX_EVENTS`, etc.)
- `cors_origins` field in `config.settings.Settings` — CORS configurable via env var,
  no longer hardcoded in `main.py`
- `infra/README.md`, `backend/api/README.md`, `backend/api/services/README.md`,
  `backend/tests/README.md` — missing module documentation

### Changed
- All `os.getenv()` calls in `backend/api/` migrated to `config.settings`
- All route files updated to import from `api.core.*` instead of shim files
  (`api.auth`, `api.database`, `api.schemas`)
- `backend/api/main.py` uses `settings.app_version`, `settings.cors_origins`,
  `settings.redis_url`, `settings.lancedb_path`, `settings.ollama_base_url` etc.
- `_run_pipeline_sync` (239 lines) moved from route handler to `pipeline_service.py`
- `_translate_sas_to_python` (154 lines) moved from route handler to `translation_service.py`
- `_SAS_CONVERSION_RULES` constant moved to `translation_service.py`
- `conversions.py` reduced from 1063 lines to ~310 lines (route handlers only)

### Fixed
- Unused `import shutil` removed from `conversions.py`
- Duplicate `from api.database import CorrectionRow` import deduplicated
- `DB_PATH` module-level variable in `main.py` replaced with `settings.sqlite_path`
  (fixes start_conversion passing a potentially stale path)

---

## [3.0.0] — 2026-04-06 (Week 13 restructure)

- 11-node orchestrator reduced to 8 composite nodes (facade pattern)
- Full repo reorganization into logical subfolders
- 44+20 audit fixes (Audit grade: A-)
- Azure Monitor telemetry, GitHub Actions CI/CD, CodeQL, Docker

## [2.0.0] — 2026-03-15 (Week 9)

- Azure OpenAI promoted to primary LLM (replaced Ollama/Groq-primary)
- RateLimitSemaphore, CircuitBreaker added
- KBWriter (LanceDB, 330 pairs)

## [1.0.0] — 2026-02-01 (Week 1-2)

- Initial FileAnalysisAgent, CrossFileDepsResolver, RegistryWriterAgent
- 50-file gold corpus (721 blocks)
