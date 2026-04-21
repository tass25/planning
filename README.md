# Codara by tess — SAS → Python Conversion Accelerator

Multi-agent SAS-to-Python conversion accelerator using LangGraph orchestration, RAPTOR semantic clustering, and a 3-tier LLM fallback chain (Nemotron via Ollama → Azure OpenAI → Groq).

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
│                                    # (docs/, planning, reports → Planning branch)
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
| 1 | **Nemotron** (`nemotron-3-super:cloud` via Ollama) | **Primary** — all risk levels |
| 2 | Azure OpenAI GPT-4o / GPT-4o-mini | Fallback 1 — when Nemotron unavailable |
| 3 | Groq LLaMA-3.3-70B (3-key pool) | Fallback 2 + cross-verifier |
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

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `OLLAMA_API_KEY` | Yes | Ollama API key (primary LLM — Nemotron) |
| `OLLAMA_BASE_URL` | No | Ollama base URL (default: `http://localhost:11434/v1`) |
| `OLLAMA_MODEL` | No | Ollama model name (default: `nemotron-3-super:cloud`) |
| `AZURE_OPENAI_API_KEY` | No | Azure OpenAI fallback key |
| `AZURE_OPENAI_ENDPOINT` | No | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_API_VERSION` | No | API version (default: `2024-10-21`) |
| `AZURE_OPENAI_DEPLOYMENT_FULL` | No | Full model deployment name (default: `gpt-4o`) |
| `AZURE_OPENAI_DEPLOYMENT_MINI` | No | Mini model deployment name (default: `gpt-4o-mini`) |
| `GROQ_API_KEY` | Yes | Groq API key (fallback 2 + cross-verifier) |
| `GROQ_API_KEY_2` | No | Groq key #2 (rotation on 429) |
| `GROQ_API_KEY_3` | No | Groq key #3 (rotation on 429) |
| `CODARA_JWT_SECRET` | Yes | JWT signing secret (256-bit hex) |
| `CODARA_ADMIN_PASSWORD` | No | Admin seed password (random if unset) |
| `CODARA_USER_PASSWORD` | No | User seed password (random if unset) |
| `REDIS_URL` | No | Redis URL (default: `redis://localhost:6379/0`) |
| `AZURE_STORAGE_CONNECTION_STRING` | No | Blob Storage (falls back to local disk) |
| `AZURE_STORAGE_CONTAINER` | No | Blob container name (default: `codara-uploads`) |
| `AZURE_QUEUE_NAME` | No | Queue name (default: `codara-pipeline-jobs`) |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | No | Azure Monitor telemetry (no-op if unset) |

## Default Credentials (dev seed)

Passwords are **randomly generated** on first boot and printed to stdout.
Pin them with env vars before first start:

```bash
CODARA_ADMIN_PASSWORD=<choose>   # → admin@codara.dev
CODARA_USER_PASSWORD=<choose>    # → user@codara.dev
```

## Documentation

Planning journals, audit reports, architecture diagrams, and research notes
live in the `Planning` branch to keep `main` focused on code.

```bash
git checkout Planning   # access docs, reports, weekly planning
```
