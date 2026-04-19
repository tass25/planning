# Session Log — 15 April 2026

---

## Wave 1 — Parallel codebase overhaul (Agents A/B/C/D)

### Agent A — Security & Auth
- `backend/api/routes/auth.py`: Added `_check_rate_limit(request, endpoint)` — 5 attempts/IP/60 s window, HTTP 429 on breach. Applied to both `/login` and `/register`.
- `backend/api/main.py`: Replaced hardcoded passwords (`admin123!` / `user123!`) with `_get_or_generate_password()` that reads `CODARA_ADMIN_PASSWORD` / `CODARA_USER_PASSWORD` env vars; falls back to `secrets.token_urlsafe(18)` printed to stdout on first boot.

### Agent B — Pipeline service extraction
- `backend/api/services/pipeline_service.py` (NEW): Extracted `run_pipeline_sync()` from `conversions.py`. Signature: `(conversion_id, file_id, filename, db_path)`. Downloads file via `blob_service.download_to_temp()`, runs 8 stages, cleans up temp file.
- Removed 4 artificial `time.sleep()` calls from stages 1–4.
- Fixed accuracy metric: derived from `translation_ok` + `syntax_ok` instead of hardcoded 100.0.

### Agent C — Translation agent cleanup
- `backend/partition/translation/translation_agent.py`:
  - Added `_LLM_TIMEOUT_S = 60` + `asyncio.wait_for()` on ALL LLM calls (Azure, Groq, cross-verify, reflection).
  - Merged duplicate `_translate_azure_4o` / `_translate_azure_mini` into shared `_translate_with_model()`.
  - Added empty-choices guard in `_generate_reflection`.
  - Removed unused imports: `os`, `datetime`, `timezone`, `get_failure_mode_rules`.
- `backend/partition/translation/translation_pipeline.py`: Added DI params (`translator`, `validator`, `z3`); removed unused `Optional` import.

### Agent D — Models & utilities
- `backend/partition/models/partition_ir.py`: Added `RAPTORNode(BaseModel)` (merged from deleted `raptor_node.py`) and `PartitionMetadata(TypedDict)` with 11 typed keys.
- `backend/partition/orchestration/telemetry.py`: Fixed `create_gauge` → `create_histogram` (OTel 1.20+ compat); tracer name `"codara.pipeline"`.
- `backend/partition/orchestration/orchestrator.py`: Removed dead `_common_parent()`, cached RAPTOR agent, removed unused `Optional` import.
- `backend/partition/utils/llm_clients.py`: Removed dead `get_llm_provider()`.
- `backend/partition/streaming/pipeline.py`: Inlined `create_queue()` from deleted `backpressure.py`.
- `backend/partition/utils/logging_config.py`: Moved from `partition/` root; updated 2 callers.
- Added `__all__` barrel exports to 4 `__init__.py` files.

### Deleted
- `backend/partition/streaming/backpressure.py` (inlined)
- `backend/partition/models/raptor_node.py` (merged into partition_ir.py)
- `backend/api/auth.py`, `backend/api/database.py`, `backend/api/schemas.py` (stale shims)

---

## Wave 2 — Azure services integration

### Blob Storage (`backend/api/services/blob_service.py` — NEW)
- `BlobStorageService`: upload / download_to_temp / list_files / delete_folder
- Uses `AZURE_STORAGE_CONNECTION_STRING` + `AZURE_STORAGE_CONTAINER`
- Graceful fallback: local disk under `backend/uploads/` when not configured

### Queue Storage (`backend/api/services/queue_service.py` — NEW)
- `PipelineQueueService`: producer + daemon consumer thread
- Enqueue: JSON payload base64-encoded → Azure Queue (visibility_timeout=0)
- Consumer: polls every 2 s, runs `run_pipeline_sync()`, deletes on success
- Poison message protection: `_MAX_DEQUEUE_COUNT = 5` → dead-letters after 5 failures
- Visibility timeout: 300 s (5 min) — Azure auto-retries if worker crashes
- Graceful fallback: BackgroundTasks when not configured

### `backend/api/routes/conversions.py`
- Upload now calls `blob_service.upload()`; filename resolved via `blob_service.list_files()`
- Start: tries `queue_service.enqueue_job()` first, falls back to `background_tasks.add_task()`
- Added `_MAX_UPLOAD_BYTES = 50 MB` and `_ALLOWED_CONTENT_TYPES` validation

### `backend/config/settings.py`
- Added: `azure_storage_connection_string`, `azure_storage_container`, `azure_queue_name`

### `backend/requirements/base.txt`
- Added: `azure-storage-blob~=12.25.0`, `azure-storage-queue~=12.12.0`
- Fixed: `opentelemetry-api~=1.36.0` (was `~=1.25.0`, caused downgrade on fresh install)

### `backend/api/main.py`
- Added startup: `_init_telemetry()` and `queue_service.start_worker()`

---

## Wave 3 — Agent G audit
- Full audit performed; grade B+ issued in `.review/final_audit.md`

---

## Azure connectivity test results

```
=== 1. Application Insights ===
telemetry_enabled  backend=azure_monitor
tracer: ENABLED
meter:  ENABLED

=== 2. Blob Storage ===
blob_storage_enabled  container=codara-uploads
enabled: True
container reachable: OK (listed 0 blobs)

=== 3. Queue Storage ===
queue_service_enabled  queue=codara-pipeline-jobs
enabled: True
enqueue test message: OK
dequeue + delete test message: OK

=== ALL AZURE SERVICES OK ===
```

### Fix applied this session
- `azure-monitor-opentelemetry~=1.6.0` was listed in requirements but not installed in venv.
- Installed via: `pip install "azure-monitor-opentelemetry~=1.6.0"` → pulled 1.6.13 + full OTel stack.
- All three Azure services now confirmed operational.

---

## Status
All Wave 1 + Wave 2 + Wave 3 work complete. All Azure services ENABLED and tested.

---

## Prompt enhancement — anti-`def` rules

### Problem
LLM was wrapping all IF/ELIF value-mapping chains in unnecessary `def` helper functions,
and sometimes wrapping whole scripts in `def main()`.

### Fix applied to 4 locations
1. `backend/partition/prompts/templates/translation_static.j2`
2. `backend/partition/prompts/templates/translation_agentic.j2`
3. `backend/partition/prompts/templates/translation_graph.j2`
4. `backend/api/services/translation_service.py` (both `_SAS_CONVERSION_RULES` and system prompt)

### Rule added (identical in all 4 locations)
- NEVER wrap IF/ELIF value-mapping in `def` — use `dict + .map()` for enums, `np.select()` / `pd.cut()` for ranges
- Script-level SAS code → top-level Python statements, NOT wrapped in `def main()` or any function
- `def` ONLY for `%MACRO` called 2+ times

## Custom KB pairs ingestion

### Source
User-provided JSON with 35 real-world SAS→Python pairs (Groupe BPCE / Teradata context).

### Script
`backend/scripts/kb/ingest_custom_pairs.py`

### Result
```
pairs_to_ingest: 20 (15 had empty python_code, skipped)
KB size: 112 -> 132
Embeddings: nomic-ai/nomic-embed-text-v1.5 (768-dim), CPU, batch=20
```

### Categories added
DATA_STEP_CONDITIONAL (×2, with correct dict+.map() pattern)
DATA_STEP_MERGE (×3), DATA_STEP_FILTER (×2), DATA_STEP_KEEP (×1)
PROC_SORT (×4), PROC_FREQ (×1), PROC_EXPORT (×3)
PROC_SQL (×1), MACRO_VARIABLE (×2), LIBNAME (×1)

---

## Nemotron fallback chain insertion

### Change
Inserted `nemotron-3-super:cloud` (Ollama cloud) as fallback 2 in the LLM chain,
between Azure (fallback 1) and Groq (fallback 3/last resort).

New chain: **Nemotron (primary) → Azure GPT-4o → Groq LLaMA-70B → PARTIAL**

### Correction (same session)
User clarified: Nemotron REPLACES minimax as primary (not a middle step).
Chain corrected to: **Nemotron → Azure → Groq**.

### Files changed
- `backend/partition/translation/translation_agent.py`:
  - `_NEMOTRON_MODEL = "nemotron-3-super:cloud"` constant
  - `self.ollama_client` now calls Nemotron model (not minimax) as step 1
  - `_translate_with_model()`: step 1 = Nemotron, step 2 = Azure, step 3 = Groq
  - Removed intermediate Nemotron fallback (was incorrectly between Azure/Groq)
  - Class docstring + module docstring updated to reflect 3-step chain
- `backend/api/services/translation_service.py`:
  - Nemotron block moved to FIRST position (primary), Azure is fallback 1, Groq is fallback 2
  - Module + function docstrings updated

---

## Teammate project analysis + feature backport

### Source
Teammate project: `code-conversion-classic-main` (same SAS→Python concept, different execution).
Analysed all files; produced comparison table of 14 features.

### Features implemented (all "worth adding" items)

#### 1. Deterministic (rule-based) translator — NEW FILE
`backend/partition/translation/deterministic_translator.py`
- 6 rule patterns handled WITHOUT LLM: PROC SORT, PROC SORT NODUPKEY, PROC IMPORT (CSV/Excel),
  PROC EXPORT (CSV/Excel), DATALINES/CARDS, simple DATA SET (copy/keep/drop/rename), PROC PRINT.
- Returns `DeterministicResult(code, reason)` or `None`.
- Injected into `TranslationAgent.process()` as Step 0 — fires before RAG/LLM.
- Produces `model_used="deterministic:<rule>"` and `rag_paradigm="deterministic"`.

#### 2. Error classifier (17 categories) — NEW FILE
`backend/partition/translation/error_classifier.py`
- Categories: SYNTAX, TIMEOUT, NAME_ERROR, IMPORT_ERROR, KEY_ERROR, COL_MISSING, TYPE_ERROR,
  VALUE_ERROR, ATTRIBUTE_ERROR, DTYPE_MISMATCH, COL_EXTRA, MERGE_CONTRACT, SORT_ORDER,
  RETAIN_SEQUENCE, LAG_SEQUENCE, GROUP_BOUNDARY, EMPTY_SUSPICIOUS, OUTPUT_MISSING, RUNTIME_GENERAL.
- `classify_error(msg, traceback, code) → ErrorReport` with `primary_category`, `all_categories`,
  `affected_columns`, `repair_hint`.
- Integrated into `ValidationAgent.validate()` — `ValidationResult` now carries `error_category`
  and `traceback` fields.

#### 3. Error analyst (root cause + repair strategy) — NEW FILE
`backend/partition/translation/error_analyst.py`
- `analyse_error(report, sas_code, python_code, partition_type) → ErrorAnalysis`.
- Per-category handlers: COL_MISSING, DTYPE_MISMATCH, MERGE_CONTRACT, RETAIN_SEQUENCE,
  LAG_SEQUENCE, GROUP_BOUNDARY, OUTPUT_MISSING, SORT_ORDER, EMPTY_SUSPICIOUS.
- Each analysis has: `root_cause`, `non_neg_contract`, `forbidden`, `repair_strategy`, `minimal_scope`.
- `analysis.to_prompt_block()` renders as Markdown block injected into correction prompt.
- Extracts SAS BY vars, MERGE type, output dataset name from SAS source for context.

#### 4. Lineage guard — NEW FILE
`backend/partition/translation/lineage_guard.py`
- `check_lineage(python_code, internal_table_names) → LineageReport`.
- Detects `pd.read_csv/read_excel/read_parquet` calls for DataFrames that should come
  from prior pipeline steps (not from disk).
- `build_internal_table_set(sas_code)` extracts all output dataset names from SAS.
- `LineageReport.to_prompt_block()` renders violations as Markdown for correction prompts.

#### 5. Hybrid retrieval (keyword + semantic) — UPGRADED `kb_query.py`
`backend/partition/translation/kb_query.py`
- Added `_keyword_vector(sas_code)`: TF-normalised cosine on 91 SAS keywords (L2-normalised).
- Hybrid score: `0.40 × keyword_cosine + 0.60 × semantic_cosine`.
- Over-fetches 3k candidates from LanceDB, re-ranks by hybrid score, returns top k.
- Added `_deduplicate_issues()`: Jaccard ≥ 0.85 dedup across KB example issue lists.
- `retrieve_examples()` now accepts `sas_code=` parameter for keyword scoring.
- `MIN_RELEVANCE` lowered 0.50 → 0.40 (keyword boost lifts lower-semantic items).

#### 6. Stagnation detection + retry budget differentiation — UPGRADED `translation_pipeline.py`
`backend/partition/translation/translation_pipeline.py`
- `_retry_budget(partition)`: base 2 + 1 for MACRO/SQL_BLOCK partitions.
- `_MAX_STAGNANT = 2`: stops retrying when consecutive corrections produce identical code.
- `_SEMANTIC_ERROR_BONUS = 1`: extra retry when syntax passes but exec fails.
- Error classification + `ErrorAnalysis` injected into `partition.metadata["error_analysis_hint"]`
  before each retry so `TranslationAgent` receives targeted guidance.
- Stagnation detection: tracks `last_code`; increments counter on no change; breaks at limit.

#### 7. TranslationAgent upgrades — UPGRADED `translation_agent.py`
`backend/partition/translation/translation_agent.py`
- **Step 0**: Try `try_deterministic()` before RAG/LLM (instant return for simple patterns).
- **Step 2**: `_enrich_business_logic()` — heuristic plain-English summary injected into
  `partition.metadata["business_logic"]`.
- **Step 2**: `_extract_sas_contract()` — extracts BY vars, KEEP/DROP, MERGE type, DESCENDING,
  NODUPKEY; appended to LLM prompt as `## SAS Contract` block.
- Error analysis hint from pipeline retry injected into prompt before LLM call.
- `model_used` default changed from `"azure_gpt4o_mini"` to `"nemotron"`.

#### 8. ValidationAgent upgrade — UPGRADED `validation_agent.py`
`backend/partition/translation/validation_agent.py`
- `ValidationResult` now has `error_category` and `traceback` fields.
- `validate()` calls `classify_error()` on both syntax and exec failures.
- Error category and traceback surfaced to `TranslationPipeline` for targeted repair.

#### 9. Regression test suite — NEW FILE
`backend/tests/test_regression.py`
- Parametrised pytest suite over all 61 gold standard `.sas` files.
- Tests: syntax validity of deterministic translations, deterministic fires for known patterns
  (simple tier), no lineage violations, no `def main()` wrappers.
- Unit tests for `ErrorClassifier` (7 cases) and `DeterministicTranslator` (8 cases).
- Unit tests for `LineageGuard` (4 cases).
- Run: `cd backend && python -m pytest tests/test_regression.py -v --tb=short`

### Summary of what was NOT taken (and why)
- **Semantic validation on witness data** (item 5/6): Requires SAS execution for ground truth.
  Our Z3 formal verification covers this more rigorously.
- **Execution state tracker** (item 10): Partial — our NetworkX dependency graph covers lineage;
  materialised column/dtype tracking adds complexity with marginal gain given Z3.
- These were "high effort, uncertain gain" given existing Z3 + RAPTOR infrastructure.

---

## 360° Audit fixes (post-rating)

### Critical bugs fixed

#### 1. `translation_pipeline.py` — hint leak on process() exception
- `partition.metadata["error_analysis_hint"]` injection now wrapped in `try/finally`
- Guarantees hint is always popped even if `translator.process()` raises mid-execution

#### 2. `translation_agent.py` — broken regex in `_enrich_business_logic()`
- Removed dead condition `proc_name.replace(" ", r"\s*")` which was always truthy
- Search now directly calls `re.search(proc_name.replace(" ", r"\s+"), code_upper)`

#### 3. `translation_agent.py` — misleading `model_used` default
- Initialised as `""` instead of `"nemotron"` — avoids wrong label in PARTIAL results

#### 4. `translation_agent.py` — renamed misleading method names
- `_translate_azure_4o` → `_translate_high_risk` (Nemotron→Azure GPT-4o→Groq)
- `_translate_azure_mini` → `_translate_low_risk` (Nemotron→Azure GPT-4o-mini→Groq)
- Updated all 3 call sites (main loop, reflexion retry, _translate_local fallback)

#### 5. `deterministic_translator.py` — silent exception swallowing
- Added `import structlog` + `logger.warning("deterministic_rule_error", ...)` in except block
- Crashes in individual rules now surface in logs instead of disappearing silently

### Architecture / dead code removed

#### 6. HyperRAPTOR removal
- `backend/partition/raptor/clustering.py`: Removed `HyperRAPTORClusterer` class (220+ lines)
  and `get_clusterer()` env-var logic; replaced with simple `get_clusterer() → GMMClusterer()`
- `backend/config/settings.py`: Removed `use_hyper_raptor: bool = False` (was unused — 
  clustering.py read `os.getenv("USE_HYPER_RAPTOR")` directly)
- `backend/requirements/base.txt`: Removed `geoopt~=0.5.0`
- `backend/tests/test_hyper_raptor.py`: Deleted

#### 7. PySpark removal
- `frontend/src/types/index.ts`: `TargetRuntime = "python" | "pyspark"` → `"python"` only
- PySpark was in the title but never implemented in the frontend or pipeline

### GitHub OAuth
- Confirmed already fully implemented via httpx (not a stub)
- `/auth/github/url` + `/auth/github/callback` both functional
- Returns HTTP 501 when `GITHUB_CLIENT_ID`/`GITHUB_CLIENT_SECRET` not configured
- No fix needed

### New files
- `.env.example`: Created with all 20 env vars documented (required vs optional)

### README.md updates
- Title changed: "SAS → Python/PySpark" → "SAS → Python"
- LLM routing table updated: Nemotron as primary (was Azure GPT-4o)
- Default credentials section updated: explains random-on-boot + env vars to pin
- Environment variables section: added 9 missing vars, added `.env.example` reference
- Added OLLAMA_BASE_URL, OLLAMA_MODEL, AZURE_* deployment names, CODARA_ADMIN/USER_PASSWORD,
  AZURE_STORAGE_*, APPLICATIONINSIGHTS_CONNECTION_STRING
