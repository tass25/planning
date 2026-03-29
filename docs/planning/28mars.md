# Week 28 Mars — Codara Changes & Updates

**Date**: 2026-03-28
**Branch**: main
**Scope**: Test suite fixes, PySpark removal, regex pattern enrichment, deliverables tooling

---

## Summary

Full audit pass following the comprehensive technical review. All changes target `main` branch only; `planning` branch is untouched.

---

## 1. Test Suite — All Tests Now Runnable with pytest

### Problem
`pytest tests/` reported 2 collection errors:
- `test_rag.py` → `ModuleNotFoundError: No module named 'tiktoken'` (cascade from `sentence_transformers` → `transformers` → `keras` → missing `tf_keras`)
- `test_raptor.py` → same cascade + `import tiktoken` at module level in `summarizer.py`

Previously: **209 collected, 2 errors** (207 runnable)
After fix: **278 collected, 0 errors** (all runnable)

### Fixes

#### `partition/raptor/embedder.py`
- Wrapped `from sentence_transformers import SentenceTransformer` in `try/except Exception`
- Module now imports cleanly even when `sentence_transformers` is broken
- `NomicEmbedder.__init__()` raises `RuntimeError` with install hint instead of failing at import time
- **Required action**: `pip install tf-keras` to use NomicEmbedder at runtime (see `requirements.txt`)

#### `partition/raptor/summarizer.py`
- Wrapped `import tiktoken` in `try/except ImportError`
- `self._enc` set to `None` when tiktoken unavailable; token counting falls back to `len(chars) // 4`
- All `self._enc.encode/decode` calls guarded with `if self._enc is not None`

#### `requirements.txt`
- Added `tf-keras>=2.16.0` (required by `sentence-transformers 4+` keras backend)

#### `tests/test_orchestration.py`
- Removed stale `sys.path.insert(0, str(_ROOT / "sas_converter"))` — pre-rename artifact, `sas_converter/` no longer exists

---

## 2. PySpark Removal — Python-Only Target

Codara is SAS → Python only. All PySpark references removed.

### Files modified

| File | Change |
|------|--------|
| `partition/merge/import_consolidator.py` | Removed `PYSPARK_IMPORTS` dict; removed `target_runtime` param from `_to_import_statement()` and `consolidate_imports()`; removed SparkSession injection |
| `partition/orchestration/state.py` | `target_runtime` comment updated to `# always "python"`; `_valid_runtime` validator now raises `ValueError` if value is not `"python"` |
| `partition/rag/static_rag.py` | Removed `"PySpark" if target_runtime == "pyspark"` ternary → constant `"Python (pandas)"` |
| `partition/rag/graph_rag.py` | Same |
| `partition/rag/agentic_rag.py` | Same (2 occurrences) |
| `partition/translation/translation_agent.py` | Removed PySpark from docstrings |
| `partition/merge/script_merger.py` | Output filename is always `_converted.py` (not `_converted_spark.py`) |
| `partition/kb/kb_writer.py` | Docstring updated from "SAS→Python/PySpark" to "SAS→Python" |
| `partition/models/conversion_result.py` | Docstring updated |
| `scripts/run_pipeline.py` | `--target` choices: `["python"]` only |
| `scripts/generate_kb_pairs.py` | Removed pyspark from prompts, CLI, and model fields |
| `tests/test_rag.py` | Removed `test_pyspark_runtime_label` test method |
| `tests/test_merge_retraining.py` | Removed `test_pyspark_adds_spark_session` test method |

---

## 3. Regex / Pattern Enrichment

### `partition/streaming/state_agent.py`
- Added `PROC_NAME` class-level regex: `re.compile(r"^\s*PROC\s+(\w+)", re.IGNORECASE)` — extracts specific PROC name from first line of any PROC block
- Added `KNOWN_PROC_TYPES: frozenset[str]` — 80+ SAS PROC names categorized (Base SAS, SAS/STAT, SAS/ACCESS, SAS/GRAPH, Analytics, SAS/CONNECT, misc). Used for metadata enrichment and complexity scoring hints.

Categories covered:
- **Base SAS**: SORT, MEANS, FREQ, PRINT, CONTENTS, DATASETS, APPEND, COPY, COMPARE, TRANSPOSE, FORMAT, CATALOG, PRINTTO, REPORT, TABULATE, UNIVARIATE, CHART, PLOT, TEMPLATE, DELETE, DISPLAY
- **SAS/STAT**: ANOVA, GLM, GLMSELECT, MIXED, GENMOD, LOGISTIC, LIFETEST, PHREG, REG, ARIMA, AUTOREG, FORECAST, ESM, EXPAND, FACTOR, CANDISC, DISCRIM, CLUSTER, FASTCLUS, ACECLUS, DISTANCE, CORRESP, CATMOD, TTEST, NPAR1WAY, CORR, HPLOGISTIC, HPSPLIT, HPBIN, LASSO, PLS, RIDGE, POWER, SEVERITY, COUNTREG, LOESS, GEE, GLIMMIX
- **SAS/ACCESS + SQL**: SQL, FEDSQL, SDSQL, DBLOAD, DBF
- **SAS/GRAPH**: GCHART, GPLOT, G3D, GANNO, GINSIDE, BOXPLOT
- **Import/Export**: IMPORT, EXPORT, CIMPORT, CPORT, UPLOAD, DOWNLOAD
- **Analytics/DataMining**: SURVEYSELECT, CAPABILITY, CHISQ, INTERACT, OUTLIER, KMEANS, GRIDDED
- **Misc**: PRINTTO, MACROS, FCMP, GEOCODE, X11, CAS, CASUTIL

### `partition/chunking/boundary_detector.py`
- Added `_PROC_NAME_RE = re.compile(r"^\s*PROC\s+(\w+)", re.IGNORECASE)` at module level
- `_emit()` now extracts the PROC name from the first line of every `PROC_BLOCK` event and stores it in `extra_metadata={"proc_type": "SORT"}` on the `BlockBoundaryEvent`

### `partition/chunking/models.py`
- Added `extra_metadata: dict = Field(default_factory=dict)` field to `BlockBoundaryEvent` — carries `{"proc_type": "SORT"}` or empty dict

### `partition/chunking/partition_builder.py`
- `proc_subtype` in `PartitionIR.metadata` now prefers `event.extra_metadata.get("proc_type")` over the regex fallback — faster, avoids double-matching

---

## 4. New Scripts

### `scripts/verify_deliverables.py`
Checks that all required project files exist. Run:
```bash
cd backend && python scripts/verify_deliverables.py
```
Reports:
- Required files (pipeline, API, prompts, tests, docs, infra)
- Optional/runtime files (lancedb_data, ablation.db)
- Gold standard corpus count (`.sas` + `.gold.json`)
- Exit code 0 if all required present, 1 if any missing

---

## 5. Benchmark Status (unchanged)

- Corpus: **822 blocks** (61 `.sas` files)
- Accuracy: **82.2%** (676/822) — PASSED ≥ 80%
- Gold standard tiers: basic (`gs_*`), medium (`gsm_*`), hard (`gsh_*`), real-world (`gsr_*`)

---

## 6. APIs / External Services Required

The following services require credentials you must provide:

| Service | Env Var | File | Purpose |
|---------|---------|------|---------|
| Azure OpenAI | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` | `.env` | Primary LLM (GPT-4o, GPT-4o-mini) |
| Azure OpenAI | `AZURE_OPENAI_DEPLOYMENT_FULL`, `AZURE_OPENAI_DEPLOYMENT_MINI` | `.env` | Deployment names |
| Azure OpenAI | `AZURE_OPENAI_API_VERSION` | `.env` | API version (e.g. `2024-10-21`) |
| Groq | `GROQ_API_KEY` | `.env` | Fallback LLM + cross-verifier (LLaMA-3.1-70b) |
| Redis | `REDIS_URL` | `.env` | Pipeline checkpointing (default: `redis://localhost:6379/0`) |
| JWT | `CODARA_JWT_SECRET` | `.env` | Auth token signing (any 32+ char secret) |
| Azure Monitor | `APPLICATIONINSIGHTS_CONNECTION_STRING` | `.env` | Optional telemetry (no-op if absent) |

**To generate additional KB pairs** (`scripts/generate_kb_pairs.py`): requires Azure OpenAI + Groq keys.
**To run the full translation pipeline**: requires Azure OpenAI + Groq keys at minimum.
**To run tests**: no API keys needed (all LLM calls are mocked).

---

## 7. Remaining Work (post 28-mars)

- [ ] KB expansion: 330 → 380 pairs (needs Azure + Groq keys)
- [ ] Ablation study plots: `python scripts/analyze_ablation.py --db ablation.db --plots`
- [ ] Defense slides
- [ ] Demo video
