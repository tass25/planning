# Codara — SAS → Python/PySpark Conversion Accelerator

Multi-agent SAS-to-Python/PySpark conversion accelerator using LangGraph orchestration, RAPTOR semantic clustering, and Azure OpenAI inference.

## Quick Start

```bash
# 1. Clone and set up
git clone <repo-url> && cd Stage
python -m venv venv
.\venv\Scripts\Activate.ps1          # Windows
pip install -r backend/requirements.txt

# 2. Configure environment
cp .env.example .env                  # Edit with your API keys

# 3. Start the backend API
cd backend
python -m uvicorn api.main:app --reload --port 8000

# 4. Start the frontend (in a separate terminal)
cd frontend
npm install
npm run dev
```

## Project Structure

```
Stage/
├── .env                         # Environment variables (all secrets)
├── docker-compose.yml           # Redis + Backend + Frontend services
├── Dockerfile                   # Backend Docker image
├── pyproject.toml               # Build/test configuration
│
├── backend/                     # Python backend
│   ├── api/                     # FastAPI REST API (auth, conversions, admin)
│   ├── partition/               # 8-stage SAS conversion pipeline
│   │   ├── entry/               # L2-A: file scan, cross-file deps, registry
│   │   ├── streaming/           # L2-B: async streaming + FSM
│   │   ├── chunking/            # L2-C: boundary detection + partitioning
│   │   ├── raptor/              # L2-C: RAPTOR semantic clustering
│   │   ├── complexity/          # L2-D: risk scoring + strategy routing
│   │   ├── persistence/         # L2-E: SQLite persistence
│   │   ├── index/               # L2-E: NetworkX DAG + SCC
│   │   ├── translation/         # L3: LLM translation + validation
│   │   ├── merge/               # L4: script assembly + reports
│   │   └── orchestration/       # LangGraph + Redis + DuckDB audit
│   ├── config/                  # Project configuration (YAML)
│   ├── scripts/                 # CLI tools (run_pipeline.py)
│   ├── tests/                   # pytest test suite
│   ├── benchmark/               # Gold standard accuracy benchmark
│   ├── knowledge_base/          # Gold standard .sas + .gold.json
│   └── examples/                # Demo pipeline + sample SAS files
│
├── frontend/                    # React + TypeScript UI
│   ├── src/
│   │   ├── pages/               # Login, Signup, Workspace, Admin
│   │   ├── components/          # Layout, UI primitives (shadcn)
│   │   ├── store/               # Zustand state management
│   │   └── lib/                 # API client, utilities
│   ├── vite.config.ts           # Dev server (port 8080, proxy → backend)
│   └── Dockerfile               # Frontend Docker image (Nginx)
│
└── docs/                        # Documentation & planning
    ├── planning/                # Weekly planning & progress
    ├── AUDIT_REPORT.md          # Codebase audit reports
    └── architecture_v2.html     # Architecture diagram
```

## Architecture (8-Node Pipeline v3.0)

```
file_process → streaming → chunking → raptor → risk_routing → persist_index → translation → merge → END
```

| Node | Agent | Layer | Purpose |
|------|-------|-------|---------|
| 1 | `FileProcessor` | L2-A | Scan files, register in SQLite, resolve cross-file deps |
| 2 | `StreamingParser` | L2-B | Async line-by-line streaming with FSM state tracking |
| 3 | `ChunkingAgent` | L2-C | Boundary detection + partition building |
| 4 | `RAPTORPartitionAgent` | L2-C | Semantic clustering (NomicEmbed + GMM) |
| 5 | `RiskRouter` | L2-D | Complexity scoring (LogReg+Platt) + strategy routing |
| 6 | `PersistenceAgent + IndexAgent` | L2-E | SQLite persistence + NetworkX DAG + SCC detection |
| 7 | `TranslationPipeline` | L3 | SAS→Python via LLM (6 failure modes) + validation |
| 8 | `MergeAgent` | L4 | Assemble final scripts + generate reports |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI + SQLAlchemy + SQLite |
| Frontend | React 18 + Vite + Tailwind + shadcn/ui |
| Orchestration | LangGraph StateGraph |
| LLM | Azure OpenAI (GPT-4o-mini / GPT-4o) |
| Embeddings | Nomic Embed v1.5 |
| Vector Store | LanceDB |
| Graph | NetworkX (SCC detection) |
| Auth | JWT (HS256) + GitHub OAuth |
| Checkpointing | Redis |
| Containerization | Docker + docker-compose |

## Running Tests

```bash
# From project root
python -m pytest backend/tests/ -v
```

## Docker

```bash
# Build and run everything (backend + frontend + Redis)
docker-compose up --build

# Access: frontend → http://localhost:8080, backend API → http://localhost:8000
```

## Environment Variables

See `.env` for the full list. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_API_KEY` | Yes | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI endpoint URL |
| `GROQ_API_KEY` | No | Groq API key (fallback LLM) |
| `CODARA_JWT_SECRET` | Yes | JWT signing secret (256-bit hex) |
| `GITHUB_CLIENT_ID` | No | GitHub OAuth App client ID |
| `GITHUB_CLIENT_SECRET` | No | GitHub OAuth App secret |
| `REDIS_URL` | No | Redis URL (default: `redis://localhost:6379/0`) |

## Branches

| Branch | Purpose |
|--------|---------|
| `main` | Production code (backend + frontend) |
| `Planning` | Planning docs and weekly progress reports |

## Exception Handling & Crash Prevention

Codara follows a **"Never Crash" policy** — every layer of the system has been hardened with defensive exception handling so that no single failure (DB error, LLM timeout, malformed data, missing dependency) can bring down the application.

### Backend API Layer (`backend/api/`)

| Mechanism | File | What it does |
|-----------|------|--------------|
| **Global Exception Handler** | `main.py` | A `@app.exception_handler(Exception)` catches ALL unhandled exceptions and returns a clean JSON `{"detail": "Internal server error"}` with a 500 status code. Raw Python tracebacks are **never** exposed to the client — they are logged server-side via `structlog`. |
| **Protected Startup Seed** | `main.py` | The `_seed()` function (which creates default users and KB entries) is wrapped in `try/except`. If the DB is locked or corrupted at boot, the app logs a warning and continues — the API still starts. |
| **Safe JSON Parsing** | `routes/conversions.py` | `_conv_to_out()` wraps every `json.loads(s.warnings)` call in `try/except (json.JSONDecodeError, TypeError)`. A single malformed stage row never crashes the entire list endpoint — it defaults to `[]`. |
| **Null-Safe Field Defaults** | `routes/conversions.py` | All fields in `ConversionOut` use `or` fallbacks (e.g., `row.file_name or "unknown"`, `row.duration or 0.0`) so `None` values from the DB never cause `TypeError`. |
| **Per-Stage Try/Except** | `routes/conversions.py` | Each `PipelineStageInfo` construction is wrapped individually — a malformed stage is skipped rather than killing the response. |
| **Post-Pipeline Bookkeeping** | `routes/conversions.py` | After the main pipeline completes, the user-count increment and notification creation are wrapped in their own `try/except`. A failure in bookkeeping never affects the conversion result. |
| **HTML Escape (XSS Prevention)** | `routes/conversions.py` | All user-supplied content (`sas_code`, `python_code`, `file_name`, `validation_report`, `merge_report`) is escaped via `html.escape()` before injection into the HTML download template. |
| **Session Cleanup** | `routes/conversions.py` | Both `session.close()` and `pipeline_engine.dispose()` are wrapped in independent `try/except` blocks so a failure in one doesn't prevent the other from executing. |
| **Email Uniqueness Check** | `routes/settings.py` | `update_profile` checks for duplicate emails before `commit()` and returns a `409 Conflict` instead of crashing with an `IntegrityError`. The `commit()` itself is wrapped with `session.rollback()` on failure. |
| **SQLAlchemy Best Practices** | `routes/notifications.py` | Changed `NotificationRow.read == False` to `.is_(False)` to eliminate the SQLAlchemy deprecation warning and ensure correct query behavior. |

### Pipeline Layer (`backend/partition/`)

| Mechanism | File | What it does |
|-----------|------|--------------|
| **DuckDB Auto-Init** | `orchestration/audit.py` | `_get_duckdb()` now runs `CREATE TABLE IF NOT EXISTS llm_audit (...)` on first connection. The `persist()` method never crashes because the table doesn't exist yet. If DuckDB fails to connect (corrupted file), it logs a warning and raises — the caller's existing `try/except` handles it. |
| **Timer Guard** | `orchestration/audit.py` | `_LLMCallTracker.succeed()` and `fail()` check `if self._start_time is not None` before computing latency. This prevents a `TypeError: unsupported operand type(s) for -: 'float' and 'NoneType'` if `start()` was never called. |
| **Memory Monitor Degradation** | `orchestration/orchestrator.py` | `MemoryMonitor()` instantiation and `configure_memory_guards()` are each wrapped in `try/except`. If system-level monitoring dependencies are missing or fail, the orchestrator still starts (with `self.memory_monitor = None`). |
| **Groq Import Guard** | `utils/llm_clients.py` | `get_groq_client()` catches `ImportError` for the `groq` package and raises a clear `RuntimeError("The 'groq' package is not installed. Install it with: pip install groq")` instead of an unexplained `ImportError` crash. |
| **Existing Protections** | Various | Redis checkpointing (`checkpoint.py`) already operates in degraded mode when Redis is unavailable. The `CircuitBreaker` and `with_retry` in `retry.py` already handle rate limits and transient failures. Each pipeline node has its own error isolation in the orchestrator. |

### Frontend (`frontend/src/`)

| Mechanism | File | What it does |
|-----------|------|--------------|
| **React Error Boundary** | `components/ErrorBoundary.tsx` | A class-based `ErrorBoundary` component wraps the entire application in `App.tsx`. If any child component throws an unhandled render error, it catches the error and displays a styled "Something went wrong" recovery page with a "Try Again" button — the user **never** sees a white screen. The error is also logged to `console.error` with the full component stack trace. |
| **Guarded Initial Fetch** | `App.tsx` | `fetchConversions()` now only fires if `getToken()` returns a value. Previously it fired unconditionally on mount, causing a `401 Unauthorized` error on every cold page load for unauthenticated users. |
| **Existing Protections** | `store/*.ts` | Both `user-store.ts` and `conversion-store.ts` already wrap all API calls in `try/catch` blocks. The polling mechanism in `conversion-store.ts` calls `stopPolling()` on error instead of crashing. The `api.ts` client catches `res.json()` parse failures and falls back to `{ detail: res.statusText }`. |

### Design Principles

1. **Log everything, crash nothing** — Errors are captured via `structlog` (backend) and `console.error` (frontend), but execution continues.
2. **Degrade gracefully** — If Redis is down, checkpointing is skipped. If MemoryMonitor fails, it's set to `None`. If a stage row is malformed, it's skipped.
3. **Isolate blast radius** — Each pipeline node, each DB write, each stage info construction has its own `try/except` so one failure doesn't cascade.
4. **Never expose internals** — The global exception handler ensures clients only ever receive `{"detail": "Internal server error"}`, never Python tracebacks.

---

## Week 14 — Boundary Detection & Gold Standard Enrichment

### StateAgent Pattern Expansion (`backend/partition/streaming/state_agent.py`)

Extended the `GLOBAL` and `GLOBAL_CORE` regex patterns to cover SAS constructs found in 372 real production files (banking/insurance/Teradata domain) that were previously undetected:

| Added Pattern | Covers |
|---------------|--------|
| `RSUBMIT` / `ENDRSUBMIT` | SAS/Connect remote execution blocks (4,659+ occurrences in corpus) |
| `DM\b` | `dm 'log' clear;` / `dm 'out' clear;` display manager statements |
| `ODS\b` | Output Delivery System statements |
| `%GLOBAL\b` / `%LOCAL\b` | Macro variable scope declarations |
| `TITLE\d*` / `FOOTNOTE\d*` | Report title and footnote statements |
| `%PUT\b` | All `%put` forms (not just `%put NOTE:/WARNING:/ERROR:`) |

`MACRO_CALL` negative lookahead updated to exclude `%GLOBAL` and `%LOCAL` so they are not misclassified as macro invocations.

### Gold Standard Corpus Expansion

Added **11 new real-world gold standard pairs** (`gsr_01` – `gsr_11`) to `backend/knowledge_base/gold_standard/`, derived from anonymised production SAS scripts. Each pair covers patterns absent from the original synthetic corpus:

| File | Blocks | Key patterns |
|------|--------|--------------|
| `gsr_01_rsubmit_basic_etl` | 14 | RSUBMIT + DATA + PROC SORT + PROC EXPORT |
| `gsr_02_rsubmit_merge_sort` | 12 | RSUBMIT + MERGE + SORT |
| `gsr_03_rsubmit_let_sql_export` | 9 | %LET + PROC SQL + PROC EXPORT |
| `gsr_04_macro_import_sql` | 6 | %MACRO + PROC IMPORT + SQL |
| `gsr_05_dm_rsubmit_sql` | 8 | DM + RSUBMIT + SQL + PROC EXPORT |
| `gsr_06_dm_rsubmit_proc_import` | 12 | DM + RSUBMIT + PROC IMPORT + SQL |
| `gsr_07_rsubmit_data_proc` | 7 | RSUBMIT + DATA + PROC EXPORT |
| `gsr_08_rsubmit_let_sql` | 3 | RSUBMIT + %LET + SQL |
| `gsr_09_rsubmit_sql_export` | 6 | RSUBMIT + long PROC SQL + PROC EXPORT |
| `gsr_10_rsubmit_options_sql` | 7 | RSUBMIT + OPTIONS + SQL + PROC EXPORT |
| `gsr_11_dm_include_libname` | 17 | DM + %INCLUDE + LIBNAME + PROC |

### Benchmark Result

| Metric | Before | After |
|--------|--------|-------|
| Corpus size | 721 blocks | 822 blocks (+101) |
| Correct | 575 | 676 |
| **Accuracy** | **79.8%** | **82.2%** |
| Status | below target | **PASSED (target ≥ 80%)** |

