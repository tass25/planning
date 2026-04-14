# Codara — SAS → Python/PySpark Conversion Accelerator

Multi-agent SAS-to-Python/PySpark conversion accelerator using LangGraph orchestration, RAPTOR semantic clustering, and a 3-tier LLM fallback chain (Ollama → Azure OpenAI → Groq).

## Quick Start

```bash
# 1. Clone and set up
git clone <repo-url> && cd Stage
python -m venv venv
.\venv\Scripts\Activate.ps1          # Windows
source venv/bin/activate             # Linux/Mac
pip install -r backend/requirements/base.txt

# 2. Configure environment
cp .env .env.local                   # Copy and edit with your API keys

# 3. Start the backend API
cd backend
python -m uvicorn api.main:app --reload --port 8000

# 4. Start the frontend (separate terminal)
cd frontend
bun install
bun run dev
```

## Docker

```bash
# Build and run everything (backend + frontend + Redis)
docker compose -f infra/docker-compose.yml up --build

# Access:
#   Frontend  → http://localhost:8080
#   Backend   → http://localhost:8000
#   Redis     → localhost:6379
```

## Project Structure

```
Stage/
├── README.md                        # This file
├── CLAUDE.md                        # AI project memory (Claude Code)
├── .env                             # Environment variables (all secrets)
├── .gitignore
├── pyproject.toml                   # Build + pytest configuration
│
├── infra/                           # Infrastructure & DevOps
│   ├── Dockerfile                   # Backend Docker image
│   ├── docker-compose.yml           # Redis + Backend + Frontend services
│   └── azure_setup.sh               # One-time Azure provisioning script
│
├── backend/                         # Python FastAPI + LangGraph pipeline
│   ├── api/                         # FastAPI REST API (auth, conversions, admin)
│   │   ├── core/                    # Auth, DB models, schemas, repositories
│   │   ├── middleware/              # Error handler, structured logging
│   │   ├── routes/                  # HTTP handlers (thin — no business logic)
│   │   └── services/                # Business logic: conversion, pipeline, translation
│   ├── config/                      # Settings (Pydantic BaseSettings) + constants
│   ├── partition/                   # 8-stage SAS conversion pipeline
│   │   ├── entry/                   # L2-A: file scan, cross-file deps, registry
│   │   ├── streaming/               # L2-B: async streaming + FSM
│   │   ├── chunking/                # L2-C: boundary detection + partitioning
│   │   ├── raptor/                  # L2-C: RAPTOR semantic clustering
│   │   ├── complexity/              # L2-D: risk scoring + strategy routing
│   │   ├── persistence/             # L2-E: SQLite persistence
│   │   ├── index/                   # L2-E: NetworkX DAG + SCC detection
│   │   ├── translation/             # L3: LLM translation + validation
│   │   ├── merge/                   # L4: script assembly + reports
│   │   ├── verification/            # Z3 SMT formal verification
│   │   └── orchestration/           # LangGraph + Redis + DuckDB audit
│   ├── config/                      # Settings (Pydantic BaseSettings + YAML) + constants
│   ├── requirements/                # Python dependencies
│   │   ├── base.txt                 # Production deps
│   │   └── dev.txt                  # Dev/test extras
│   ├── scripts/                     # CLI tools
│   │   ├── ops/                     # run_pipeline.py, verify_deliverables.py
│   │   ├── eval/                    # translate_test.py, run_benchmark.py
│   │   ├── ablation/                # run_ablation_study.py
│   │   └── kb/                      # generate_kb_pairs.py, expand_kb.py
│   ├── tests/                       # pytest test suite (248 tests)
│   ├── benchmark/                   # Gold standard accuracy benchmark
│   ├── knowledge_base/              # Gold standard .sas + .gold.json pairs
│   │   ├── gold_standard/           # 45+ annotated SAS/Python pairs
│   │   └── output/                  # Benchmark run outputs
│   ├── data/                        # Runtime data (gitignored)
│   │   ├── lancedb/                 # Vector KB (768-dim Nomic embeddings)
│   │   ├── analytics.duckdb         # LLM audit logs
│   │   ├── codara_api.db            # SQLite API database
│   │   ├── ablation.db              # Ablation study results
│   │   └── output/                  # Pipeline output files
│   └── examples/                    # Demo pipeline + sample SAS files
│
├── frontend/                        # React 18 + TypeScript UI
│   ├── src/
│   │   ├── pages/                   # Login, Workspace, Dashboard, Admin
│   │   ├── components/              # UI primitives (shadcn/ui)
│   │   ├── store/                   # Zustand state management
│   │   └── lib/                     # API client, utilities
│   ├── vite.config.ts               # Dev server (port 5173, proxy → :8000)
│   └── Dockerfile                   # Frontend Docker image (Nginx)
│
├── docs/                            # Documentation
│   ├── guides/                      # Technical guides
│   │   ├── 5av.md                   # Full technical changelog
│   │   ├── ROADMAP.md               # Feature roadmap
│   │   ├── global.md                # Global architecture doc
│   │   └── raptor_paper_notes.md    # RAPTOR research notes
│   ├── reports/                     # Audit reports & benchmarks
│   │   ├── AUDIT_REPORT_V3.md       # Latest audit
│   │   ├── ablation_results.md      # RAPTOR vs flat-index ablation
│   │   └── cahier_des_charges.tex   # Project specification (LaTeX)
│   ├── planning/                    # Weekly planning docs
│   │   ├── week-*.md                # Week-by-week plans
│   │   └── kanbanV2.md              # Kanban board
│   └── assets/                      # Diagrams and HTML docs
│       └── architecture_v2.html     # Architecture diagram
│
└── notebooks/                       # Jupyter / Colab notebooks
    └── fine_tune_qwen25_coder_sas.py  # QLoRA fine-tuning (Colab T4)
```

## Architecture (8-Node Pipeline v3.1)

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
| 7 | `TranslationPipeline` | L3 | SAS→Python via LLM (RAG + Z3 verification) |
| 8 | `MergeAgent` | L4 | Assemble final scripts + generate reports |

## LLM Routing

| Tier | Provider | When used |
|------|----------|-----------|
| 0 | Local GGUF (llama-cpp) | LOW risk, if fine-tuned model available |
| 1 | Azure OpenAI GPT-4o-mini / GPT-4o | All risk levels (primary) |
| 2 | Groq LLaMA-3.3-70B (3-key pool) | Fallback + cross-verifier |
| — | PARTIAL | All providers exhausted |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | FastAPI + SQLAlchemy + SQLite |
| Frontend | React 18 + Vite + Tailwind + shadcn/ui |
| Orchestration | LangGraph StateGraph |
| LLM | Azure OpenAI / Groq / Ollama (OpenAI-compat) |
| Embeddings | Nomic Embed v1.5 (768-dim) |
| Vector Store | LanceDB |
| Graph | NetworkX (SCC detection) |
| Auth | JWT (HS256) + GitHub OAuth |
| Checkpointing | Redis |
| Containerization | Docker + Compose (in `infra/`) |

## Running Tests

```bash
cd backend
python -m pytest tests/ -v --tb=short
```

## Environment Variables

All variables live in `.env` at project root. Key ones:

| Variable | Required | Description |
|----------|----------|-------------|
| `OLLAMA_API_KEY` | Yes | Ollama API key (primary LLM) |
| `AZURE_OPENAI_API_KEY` | No | Azure OpenAI fallback |
| `AZURE_OPENAI_ENDPOINT` | No | Azure OpenAI endpoint URL |
| `GROQ_API_KEY` | Yes | Groq API key (fallback + verifier) |
| `GROQ_API_KEY_2` | No | Groq key #2 (rotation on 429) |
| `GROQ_API_KEY_3` | No | Groq key #3 (rotation on 429) |
| `CODARA_JWT_SECRET` | Yes | JWT signing secret (256-bit hex) |
| `REDIS_URL` | No | Redis URL (default: `redis://localhost:6379/0`) |
| `SQLITE_PATH` | No | SQLite DB path (default: `data/codara_api.db`) |
| `DUCKDB_PATH` | No | DuckDB path (default: `data/analytics.duckdb`) |
| `LANCEDB_PATH` | No | LanceDB path (default: `data/lancedb`) |
| `CORS_ORIGINS` | No | Comma-separated allowed origins (default: localhost 8080/5173) |

## Default Credentials (dev seed)

| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@codara.dev` | `admin123!` |
| User | `user@codara.dev` | `user123!` |

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.
