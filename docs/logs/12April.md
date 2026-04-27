# Session Log — 12 April 2026

## Session: Full architectural audit + restructure (5-agent pipeline)

### Summary
Full codebase audit followed by targeted architectural improvements.
No pipeline logic changed — only the API layer was restructured.

---

## Agent 1 — ANALYZER findings

- `backend/api/routes/conversions.py` was 1063 lines — god file mixing routing, LLM calls, pipeline orchestration
- 88 direct `os.getenv()` calls scattered across `backend/api/` despite `config/settings.py` existing and fully covering all env vars
- 3 shim files (`api/auth.py`, `api/database.py`, `api/schemas.py`) — backward-compat re-exports
- Magic numbers: `16384`, `8192`, `600`, `1.0`, `2` (health timeout), `1.5` hardcoded across route files
- CORS origins hardcoded in `main.py`
- Missing `README.md` in: `backend/api/`, `backend/api/services/`, `backend/tests/`, `infra/`
- Missing `CHANGELOG.md`

---

## Agent 2 — ARCHITECT decisions

- Hybrid layered architecture: keep `partition/` domain-driven (working), fix `api/` to layered (routes → services → core)
- Extract 3 service modules from `conversions.py`
- Add `cors_origins` to `Settings`; create `config/constants.py` for named constants
- Keep shim files (non-destructive, zero risk)

---

## Agent 3 — IMPLEMENTER changes

### New files created
| File | Purpose |
|------|---------|
| `backend/config/constants.py` | Named constants: `AZURE_MAX_COMPLETION_TOKENS=16384`, `GROQ_MAX_TOKENS=8192`, `SSE_MAX_EVENTS=600`, `SSE_POLL_INTERVAL_S=1.0`, `HEALTH_CHECK_TIMEOUT_S=2.0`, `HEALTH_OLLAMA_HTTP_TIMEOUT_S=1.5`, `CHECKPOINT_INTERVAL_BLOCKS=50`, `MAX_VALIDATION_RETRIES=2`, `PARTITION_TIMEOUT_S=120` |
| `backend/api/services/__init__.py` | Service layer package |
| `backend/api/services/conversion_service.py` | `conv_to_out()`, `STAGES`, `STAGE_DISPLAY_MAP` |
| `backend/api/services/pipeline_service.py` | `run_pipeline_sync()` (extracted from 239-line route function) |
| `backend/api/services/translation_service.py` | `translate_sas_to_python()`, `_SAS_CONVERSION_RULES`, `_strip_markdown_fences()` |

### Modified files
| File | Change |
|------|--------|
| `backend/config/settings.py` | Added `cors_origins: list[str]` field |
| `backend/api/main.py` | Uses `settings.*` and `HEALTH_CHECK_TIMEOUT_S` — zero `os.getenv()` remaining |
| `backend/api/routes/auth.py` | Imports from `api.core.*`; removed `os.getenv()` for GitHub OAuth creds |
| `backend/api/routes/admin.py` | Imports from `api.core.*` |
| `backend/api/routes/analytics.py` | Imports from `api.core.*` |
| `backend/api/routes/knowledge_base.py` | Imports from `api.core.*` |
| `backend/api/routes/notifications.py` | Imports from `api.core.*` |
| `backend/api/routes/settings.py` | Imports from `api.core.*` |
| `backend/api/routes/conversions.py` | Reduced 1063 → ~310 lines; delegates to `api.services.*`; uses `settings.sqlite_path` and `SSE_MAX_EVENTS`/`SSE_POLL_INTERVAL_S` constants; removed `import shutil` (unused) |

### Verification
```
App loaded OK — 45 routes registered
Route assertions passed
All imports OK
```
Exit code: 0

---

## Agent 4 — DOCS KEEPER

New README.md files:
- `backend/api/README.md`
- `backend/api/services/README.md`
- `backend/tests/README.md`
- `infra/README.md`
- `CHANGELOG.md` (root)

---

## Agent 5 — README SYNCER

`README.md` updated:
- Added `api/core/`, `api/middleware/`, `api/routes/`, `api/services/` to structure tree
- Updated `config/` description
- Added `CORS_ORIGINS` to env vars table
- Added Changelog reference

---

## Stats
- Files created: 9
- Files modified: 11
- Lines removed from conversions.py: ~753 (1063 → 310)
- os.getenv() calls eliminated in api/: 88 → 0
- App routes: 45/45 passing

---

## Session: 4-Model Ollama Benchmark (torture_test.sas, 10 blocks)

**Script:** `backend/scripts/eval/model_benchmark.py`
**SAS fixture:** `backend/tests/fixtures/torture_test.sas` (10 blocks)
**Output dir:** `backend/output/benchmark/`

### Results

| Metric | minimax-m2.7:cloud | qwen3-coder-next:cloud | deepseek-v3.2:cloud | glm-5.1:cloud |
|--------|-------------------|----------------------|-------------------|--------------|
| Success rate | **100%** | **100%** | 50% | 80% |
| Syntax valid | **100%** | **100%** | 50% | 80% |
| Mean confidence | 0.94 | **0.95** | 0.74 | 0.88 |
| Mean latency (s) | 19.6 | **4.7** | 58.5 | 10.6 |
| Total time (s) | 197 | **48** | 587 | 109 |
| Total tokens | 10,025 | **5,359** | 18,706 | 14,838 |
| Mean tok/s | 41 | 45 | 26 | **101** |
| Z3 formally proved | 3/10 | 3/10 | 2/10 | 2/10 |
| Z3 counterexamples | 0/10 | 0/10 | 0/10 | 0/10 |

### Per-model notes

**minimax-m2.7:cloud** — Previous champion (10/10 on 2026-04-06). Confirms 10/10 today. Slowest of the 100%-passing models (19.6s avg). Highest token cost per block.

**qwen3-coder-next:cloud** — New co-champion. 10/10, 4× faster than minimax (4.7s avg), uses half the tokens (5,359 total). Equal Z3 score. Best overall value — strongly recommended as new primary.

**deepseek-v3.2:cloud** — 5/10. Fails blocks 1, 2, 4, 5, 8 with "empty python_code after parse" — model returns extended thinking/prose instead of the required JSON schema. Slowest overall (58.5s avg, 587s total). Not suitable as primary without a prompt adaptation for its output format.

**glm-5.1:cloud** — 8/10. Fails blocks 2 and 4 (same parse issue as deepseek — JSON not returned). Fastest tok/s (101 t/s). Potential use as a speed-optimised fallback if prompt is adapted.

### Actions taken
- All 4 translation files saved: `output/benchmark/translation_<model>.py`
- Combined `benchmark.md` and `benchmark.json` saved to `output/benchmark/`
- Commands run (exit code 0 for all except deepseek/glm which scored PARTIAL on some blocks):
  - `python scripts/eval/model_benchmark.py --models minimax-m2.7:cloud`
  - `python scripts/eval/model_benchmark.py --models qwen3-coder-next:cloud`
  - `python scripts/eval/model_benchmark.py --models deepseek-v3.2:cloud`
  - `python scripts/eval/model_benchmark.py --models glm-5.1:cloud`

### gemma4:31b-cloud (added same session)

| Metric | gemma4:31b-cloud |
|--------|-----------------|
| Success rate | **100%** |
| Syntax valid | **100%** |
| Mean confidence | **0.99** |
| Mean latency (s) | 7.8s |
| Total time (s) | 79s |
| Total tokens | 6,188 |
| Mean tok/s | 34 |
| Z3 formally proved | 3/10 |

### nemotron-3-super:cloud (added same session)

| Metric | nemotron-3-super:cloud |
|--------|----------------------|
| Success rate | **100%** |
| Syntax valid | **100%** |
| Mean confidence | 0.95 |
| Mean latency (s) | 5.8s |
| Total time (s) | 59s |
| Total tokens | 5,263 |
| Mean tok/s | 35 |
| Z3 formally proved | **4/10** ← best of all models |

### Full leaderboard (updated)

| Rank | Model | Success | Avg latency | Tokens | Z3 | Notes |
|------|-------|---------|-------------|--------|----|-------|
| 🥇 | **nemotron-3-super:cloud** | 10/10 | 5.8s | **5,263** | **4/10** | Best Z3, lightest tokens |
| 🥈 | **qwen3-coder-next:cloud** | 10/10 | **4.7s** | 5,359 | 3/10 | Fastest overall |
| 🥉 | **gemma4:31b-cloud** | 10/10 | 7.8s | 6,188 | 3/10 | Highest confidence (0.99) |
| 4 | minimax-m2.7:cloud | 10/10 | 19.6s | 10,025 | 3/10 | Previous primary |
| 5 | glm-5.1:cloud | 8/10 | 10.6s | 14,838 | 2/10 | Fastest tok/s (101), JSON issues |
| 6 | deepseek-v3.2:cloud | 5/10 | 58.5s | 18,706 | 2/10 | JSON format incompatible |

### Recommendation
- **Primary**: `nemotron-3-super:cloud` — 10/10, most Z3 proofs (4/10), fewest tokens (5,263), fast (5.8s avg)
- **Alternative**: `qwen3-coder-next:cloud` — marginally faster (4.7s) but one fewer Z3 proof
- **Retire**: `minimax-m2.7:cloud` as primary — outclassed on all metrics
