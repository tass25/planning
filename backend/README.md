# Codara Backend

FastAPI backend for the Codara SAS-to-Python conversion platform.

## Structure

```
backend/
├── api/                    # FastAPI REST API
│   ├── main.py             # App entrypoint (uvicorn)
│   ├── auth.py             # JWT authentication
│   ├── database.py         # SQLAlchemy models + SQLite
│   ├── schemas.py          # Pydantic request/response models
│   └── routes/             # API route handlers
│       ├── auth.py         # Login, signup, GitHub OAuth, email verification
│       ├── conversions.py  # File upload, pipeline trigger, downloads
│       ├── knowledge_base.py # KB CRUD
│       ├── admin.py        # Admin endpoints
│       ├── analytics.py    # Usage analytics
│       ├── notifications.py # User notifications
│       └── settings.py     # App settings
├── partition/              # 8-stage SAS conversion pipeline
│   ├── entry/              # L2-A: File scan, cross-file deps, registry
│   ├── streaming/          # L2-B: Async streaming + FSM
│   ├── chunking/           # L2-C: Boundary detection + partitioning
│   ├── raptor/             # L2-C: RAPTOR semantic clustering
│   ├── complexity/         # L2-D: Risk scoring + strategy routing
│   ├── persistence/        # L2-E: SQLite persistence
│   ├── index/              # L2-E: NetworkX DAG + SCC
│   ├── translation/        # L3: LLM translation + validation
│   ├── merge/              # L4: Script assembly + reports
│   ├── orchestration/      # LangGraph + Redis + DuckDB audit
│   ├── models/             # Pydantic models
│   ├── db/                 # SQLite + DuckDB managers
│   └── utils/              # LLM clients, retry, large file handling
├── config/                 # Project configuration (YAML)
├── scripts/                # CLI tools (run_pipeline.py, KB management)
├── tests/                  # pytest test suite
├── benchmark/              # Gold standard accuracy benchmark
├── examples/               # Demo pipeline + sample SAS files
├── knowledge_base/         # Gold standard .sas + .gold.json files
└── uploads/                # User uploaded SAS files (runtime)
```

## Quick Start

```bash
# From project root (Stage/)
pip install -r backend/requirements.txt

# Start the API server
cd backend
python -m uvicorn api.main:app --reload --port 8000

# Run the pipeline CLI
python scripts/run_pipeline.py path/to/file.sas --target python

# Run tests
python -m pytest tests/ -v
```

## Environment

The backend reads environment variables from the root `.env` file automatically.
See the root `.env` for all required variables (LLM keys, JWT secret, GitHub OAuth).

## Exception Handling

The backend follows a **"Never Crash" policy**. Every route, background task, and external call is wrapped in defensive error handling.

### Global Exception Handler (`main.py`)

A `@app.exception_handler(Exception)` is registered at the app level. It catches **any** unhandled exception from any route and returns a clean JSON response:

```json
{ "detail": "Internal server error" }
```

The full traceback is logged server-side via `structlog` but **never** exposed to the client. This is the last line of defense — if every other `try/except` somehow misses, this catches it.

### Protected Startup (`main.py`)

The `_seed()` function (which creates default users and KB entries on first boot) is wrapped in `try/except`. If the SQLite database is locked, corrupted, or the disk is full, the app logs a warning and continues booting — the API is still accessible.

### Route-Level Protections

| Route File | Protection | Detail |
|------------|-----------|--------|
| `conversions.py` | **Safe JSON parsing** | `json.loads(s.warnings)` in `_conv_to_out()` is wrapped in `try/except (json.JSONDecodeError, TypeError)`. A malformed warnings column defaults to `[]` instead of crashing the list endpoint. |
| `conversions.py` | **Null-safe defaults** | All `ConversionOut` fields use `or` fallbacks (`row.file_name or "unknown"`, `row.duration or 0.0`). A `None` value from the DB never causes a `TypeError`. |
| `conversions.py` | **Per-stage isolation** | Each `PipelineStageInfo` construction has its own `try/except`. One corrupt stage row is skipped — the other 7 stages still render. |
| `conversions.py` | **Post-pipeline bookkeeping** | After pipeline completion, the user-count increment and notification creation are wrapped in `try/except`. A DB failure in bookkeeping (e.g., FK violation) is logged but never affects the conversion result. |
| `conversions.py` | **HTML escape (XSS)** | All user-supplied content (`sas_code`, `python_code`, `file_name`, reports) is escaped via `html.escape()` before injection into the HTML download template. Prevents script injection. |
| `conversions.py` | **Session cleanup** | `session.close()` and `pipeline_engine.dispose()` are each in their own `try/except`. One failing doesn't block the other. |
| `settings.py` | **Email uniqueness** | `update_profile` checks for duplicate emails before `commit()`, returning `409 Conflict` instead of an `IntegrityError` crash. The `commit()` itself is wrapped with `session.rollback()` on failure. |
| `notifications.py` | **SQLAlchemy fix** | Changed `NotificationRow.read == False` to `.is_(False)` — eliminates a deprecation warning and ensures correct boolean comparison. |
| `admin.py` | **Delete user endpoint** | Added missing `DELETE /admin/users/{user_id}` with error handling: prevents self-deletion, wraps `session.delete()` + `commit()` in try/except with rollback. |

