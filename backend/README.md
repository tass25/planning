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
