# Week 9 Done: Robustness + Knowledge Base Generation

> **Layer**: Robustness + KB  
> **Branch**: `main`  
> **Status**: COMPLETE  
> **Tests**: 144 passing (38 new robustness/KB + 106 existing)  
> **Dependencies added**: psutil >= 5.9, pytest-asyncio >= 0.23  
> **Commit**: `be15d49`  

---

## Summary

Two objectives completed this week:

**Part A — Robustness Hardening**: Added retry/circuit-breaker/rate-limiter primitives and large-file memory guards to protect the pipeline against LLM API failures and memory exhaustion on large SAS files.

**Part B — Knowledge Base Generation**: Built the dual-LLM KB generation pipeline, LanceDB writer, DuckDB changelog, and rollback tooling. The generation chain uses Azure OpenAI GPT-4o (primary) for SAS generation + Python conversion, and Groq LLaMA-3.1-70B (separate context) for cross-verification.

---

## Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `partition/utils/__init__.py` | Package init | 2 |
| `partition/utils/retry.py` | `RateLimitSemaphore` + `CircuitBreaker` + global instances | ~170 |
| `partition/utils/large_file.py` | `detect_file_size_strategy()`, `checkpoint_interval()`, `configure_memory_guards()`, `MemoryMonitor` | ~150 |
| `partition/utils/README.md` | Utils module documentation | 50 |
| `partition/kb/__init__.py` | Package init | 2 |
| `partition/kb/kb_writer.py` | `KBWriter` — LanceDB `sas_python_examples` table (IVF-64 cosine index) | ~150 |
| `partition/kb/kb_changelog.py` | `log_kb_change()` + `get_history()` — DuckDB mutation audit trail | ~120 |
| `partition/kb/README.md` | KB module documentation | 65 |
| `scripts/generate_kb_pairs.py` | Dual-LLM KB generation pipeline CLI (Azure GPT-4o + Groq verifier) | ~370 |
| `scripts/kb_rollback.py` | Version rollback script for KB examples | ~110 |
| `tests/test_robustness_kb.py` | 38 test cases for all Week 9 components | ~435 |

## Files Modified

| File | Change |
|------|--------|
| `partition/chunking/boundary_detector.py` | Added `azure_breaker` + `azure_limiter` wrappers around LLM resolve calls |
| `partition/orchestration/orchestrator.py` | Added `MemoryMonitor` instance + `configure_memory_guards()` in `__init__` |
| `requirements.txt` | Added `psutil>=5.9`, `pytest-asyncio>=0.23` |

---

## Part A: Robustness Hardening

### RateLimitSemaphore

Async context manager for LLM API concurrency control:

| Provider | Max Concurrent | Rationale |
|----------|---------------|-----------|
| Azure OpenAI | 10 | Generous student-tier limits (~60 RPM) |
| Groq | 3 | Conservative for 30 RPM free tier |

```python
from partition.utils.retry import azure_limiter
async with azure_limiter:
    result = await llm_call()
```

### CircuitBreaker

Three-state pattern (CLOSED → OPEN → HALF_OPEN → CLOSED):

| Provider | Failure Threshold | Reset Timeout |
|----------|------------------|---------------|
| Azure OpenAI | 5 failures | 60 seconds |
| Groq | 3 failures | 120 seconds |

```python
from partition.utils.retry import azure_breaker
if azure_breaker.allow_request():
    try:
        result = await llm_call()
        azure_breaker.record_success()
    except Exception:
        azure_breaker.record_failure()
        raise
```

### File-Size Strategy

| Strategy | Line Count | Checkpoint Interval | RAPTOR Strategy |
|----------|-----------|-------------------|-----------------|
| Standard | < 10,000 | Every 50 blocks | Full (LOW/MOD/HIGH) |
| Large | 10,000–50,000 | Every 25 blocks | Full |
| Huge | > 50,000 | Every 10 blocks | HIGH-only |

### Memory Guards

- `PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128` — prevents CUDA memory fragmentation
- `OMP_NUM_THREADS=4` — limits OpenMP parallelism (sentence-transformers)
- `MemoryMonitor` — psutil-based RSS tracking, warns if > 100 MB

### Integration Points

- `boundary_detector.py` — LLM calls wrapped with `azure_breaker.allow_request()` + `async with azure_limiter:`
- `orchestrator.py` — `configure_memory_guards()` called at startup, `MemoryMonitor` instance created

---

## Part B: Knowledge Base Generation

### Dual-LLM Chain Architecture

```
┌──────────────────────────────┐
│  generate_kb_pairs.py        │
│                              │
│  Prompt A: Generate SAS      │──── Azure OpenAI GPT-4o
│  Prompt B: Convert → Python  │──── Azure OpenAI GPT-4o
│  Prompt C: Cross-verify      │──── Groq LLaMA-3.1-70B
└──────────────┬───────────────┘
               │ verified pairs (confidence ≥ 0.85)
               ▼
┌─────────────────────┐     ┌──────────────────────┐
│  KBWriter           │     │  kb_changelog         │
│  LanceDB table:     │     │  DuckDB table:        │
│  sas_python_examples│     │  kb_changelog         │
│  768-dim Nomic      │     │  (insert/update/      │
│  IVF-64 cosine      │     │   rollback audit)     │
└─────────────────────┘     └──────────────────────┘
```

### Azure Migration in KB Generation

| Component | Planning (Pre-Azure) | Implementation (Post-Azure) |
|-----------|---------------------|----------------------------|
| Prompt A (SAS gen) | Groq LLaMA 70B | **Azure OpenAI GPT-4o** |
| Prompt B (Python conv) | Groq LLaMA 70B | **Azure OpenAI GPT-4o** |
| Prompt C (cross-verify) | Ollama LLaMA 8B | **Groq LLaMA 3.1 70B** |

Rationale: The verifier **must** be a different provider to avoid confirming its own errors.

### Coverage Matrix (15 SAS Categories)

| Category | Target Pairs | Failure Mode |
|----------|-------------|--------------|
| DATA_STEP_BASIC | 30 | — |
| DATA_STEP_MERGE | 25 | MERGE_SEMANTICS |
| DATA_STEP_RETAIN | 20 | RETAIN |
| DATA_STEP_ARRAY | 20 | — |
| DATA_STEP_FIRST_LAST | 25 | FIRST_LAST |
| DATE_ARITHMETIC | 30 | DATE_ARITHMETIC |
| PROC_SQL | 30 | — |
| PROC_MEANS | 20 | PROC_MEANS_OUTPUT |
| PROC_FREQ | 15 | — |
| MACRO_BASIC | 25 | — |
| MACRO_CONDITIONAL | 20 | — |
| PROC_SORT | 15 | — |
| PROC_REG_LOGISTIC | 20 | — |
| PROC_IMPORT_EXPORT | 15 | — |
| MISSING_VALUE_HANDLING | 20 | MISSING_VALUE_COMPARISON |

### 6 Failure Modes (10 targeted pairs each)

| Failure Mode | Known Pitfall |
|-------------|---------------|
| RETAIN | `shift()` misused as RETAIN replacement |
| FIRST_LAST | BY-group boundary detection differs |
| DATE_ARITHMETIC | SAS epoch 1960 vs Python epoch 1970 |
| MERGE_SEMANTICS | SAS sequential merge vs pandas join |
| MISSING_VALUE_COMPARISON | SAS missing = -∞, Python NaN ≠ anything |
| PROC_MEANS_OUTPUT | _TYPE_/_FREQ_ columns + NWAY semantics |

### KB Schema (16 fields)

| Field | Type |
|-------|------|
| example_id | string (UUID) |
| sas_code | string |
| python_code | string |
| embedding | float32[768] |
| partition_type | string |
| complexity_tier | string (LOW/MOD/HIGH) |
| target_runtime | string (python/pyspark) |
| verified | bool |
| source | string |
| failure_mode | string |
| verification_method | string |

---

## ⚠️ Post-Consolidation Update (Week 13)

- **Ollama dead code paths removed** — Azure OpenAI is now the primary LLM, Groq is fallback only.
- Circuit breaker and rate limiter still active but configured for Azure OpenAI (10 concurrent) and Groq (3 concurrent).
- `opencensus-ext-azure` dependency removed, replaced by `azure-monitor-opentelemetry`.
- See [week13Done.md](week13Done.md) for full consolidation details.
| verification_score | float32 |
| category | string |
| version | int32 |
| superseded_by | string |
| created_at | string (ISO 8601) |

### Pydantic Output Models

- `GeneratedSAS` — Prompt A output (sas_code, category, complexity_tier, failure_mode, description)
- `ConvertedPython` — Prompt B output (python_code, target_runtime, imports_needed, notes)
- `CrossVerifyResult` — Prompt C output (equivalent, issues, confidence)

---

## Test Results

```
tests/test_robustness_kb.py — 38 passed

TestRateLimitSemaphore:     5 tests ✓
TestCircuitBreaker:         8 tests ✓
TestFileSizeStrategy:       5 tests ✓
TestCheckpointInterval:     4 tests ✓
TestMemoryMonitor:          4 tests ✓
TestMemoryGuards:           2 tests ✓
TestKBChangelog:            4 tests ✓
TestKBWriter:               6 tests ✓
```

Full suite: **144 passed** (2 pre-existing failures: missing langgraph + tensorflow deps)

---

## Checklist

- [x] `partition/utils/retry.py` — Rate limiter + circuit breaker
- [x] `partition/utils/large_file.py` — File-size strategy + memory guards
- [x] Retry wrappers applied to BoundaryDetector (azure_breaker + azure_limiter)
- [x] Memory guards integrated in orchestrator.__init__
- [x] `scripts/generate_kb_pairs.py` — Dual-LLM KB generation (Azure primary)
- [x] `partition/kb/kb_writer.py` — LanceDB writer with IVF-64 index
- [x] `partition/kb/kb_changelog.py` — DuckDB changelog logger
- [x] `scripts/kb_rollback.py` — Version rollback script
- [x] KB schema: 16 fields, 768-dim embeddings
- [x] Coverage matrix: 15 categories + 6 failure modes
- [x] Cross-verification threshold: confidence ≥ 0.85
- [x] 38 new tests passing
- [x] Per-folder READMEs for utils/ and kb/

---

> *Week 9 Complete → Pipeline hardened with retry/circuit-breaker/rate-limiter. KB generation tooling ready with Azure OpenAI primary + Groq cross-verification. Next: TranslationAgent + ValidationAgent (Week 10).*
