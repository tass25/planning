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
| `planning` | Planning docs and weekly progress reports |
