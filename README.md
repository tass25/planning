# SAS → Python/PySpark Conversion Accelerator

![CI](https://github.com/<YOUR_GITHUB_USERNAME>/sas-converter/actions/workflows/ci.yml/badge.svg)

Multi-agent SAS-to-Python/PySpark conversion accelerator using LangGraph orchestration, RAPTOR semantic clustering, and Azure OpenAI inference.

## Quick Start

```bash
# 1. Clone and set up
git clone <repo-url> && cd Stage
python -m venv venv
.\venv\Scripts\Activate.ps1          # Windows
pip install -r sas_converter/requirements.txt

# 2. Configure environment
cp .env.example .env                  # Edit with your API keys

# 3. Run the pipeline
python scripts/run_pipeline.py data/sas_files/ --target python
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
| Orchestration | LangGraph StateGraph |
| LLM Inference | Azure OpenAI (GPT-4o-mini / GPT-4o tiered routing) |
| Embeddings | Nomic Embed v1.5 |
| Vector Store | LanceDB |
| Relational DB | SQLite (WAL mode) |
| Analytics DB | DuckDB |
| Graph DB | NetworkX (SCC detection, multi-hop traversal) |
| Checkpointing | Redis (every 50 blocks, 24h TTL) |
| ML | scikit-learn (LogReg + Platt scaling, ECE < 0.08) |
| Telemetry | Azure Monitor + OpenTelemetry |
| CI/CD | GitHub Actions (tests + CodeQL + Dependabot) |
| Containerization | Docker multi-stage build + docker-compose |

## Project Structure

```
Stage/
├── .env.example                 # Environment template (copy to .env)
├── Dockerfile                   # Multi-stage production build
├── docker-compose.yml           # Redis + pipeline service
├── pyproject.toml               # Build/test configuration
├── scripts/
│   └── run_pipeline.py          # ★ Primary CLI entry point
├── sas_converter/
│   ├── requirements.txt         # Single source of truth for all deps
│   ├── config/                  # Project configuration (YAML)
│   ├── partition/
│   │   ├── entry/               # L2-A: file scan, cross-file deps, registry
│   │   ├── streaming/           # L2-B: async streaming + FSM
│   │   ├── chunking/            # L2-C: boundary detection + partitioning
│   │   ├── raptor/              # L2-C: RAPTOR semantic clustering
│   │   ├── complexity/          # L2-D: risk scoring + strategy routing
│   │   ├── persistence/         # L2-E: SQLite persistence
│   │   ├── index/               # L2-E: NetworkX DAG + SCC
│   │   ├── translation/         # L3: LLM translation + validation
│   │   ├── merge/               # L4: script assembly + reports
│   │   ├── orchestration/       # LangGraph + Redis + DuckDB audit
│   │   ├── models/              # Pydantic models
│   │   ├── db/                  # SQLite + DuckDB managers
│   │   └── utils/               # LLM clients, retry, large file handling
│   ├── tests/                   # 200+ pytest tests
│   ├── benchmark/               # Gold standard accuracy benchmark
│   ├── knowledge_base/          # 50 gold .sas + .gold.json files
│   └── examples/                # Demo pipeline + sample SAS
├── planning/                    # Planning docs and weekly reports
└── main.py                      # DEPRECATED — use run_pipeline.py
```

## Running Tests

```bash
cd sas_converter
$env:PYTHONPATH = "$PWD"
../venv/Scripts/python -m pytest tests/ -v
```

## Docker

```bash
# Build and run with Redis
docker-compose up --build

# Run pipeline in container
docker-compose run pipeline python scripts/run_pipeline.py /app/data/ --target python
```

## Environment Variables

See [.env.example](.env.example) for the full list. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_API_KEY` | Yes | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT_MINI` | No | GPT-4o-mini deployment name (default: `gpt-4o-mini`) |
| `AZURE_OPENAI_DEPLOYMENT_FULL` | No | GPT-4o deployment name (default: `gpt-4o`) |
| `GROQ_API_KEY` | No | Groq API key (fallback LLM) |
| `REDIS_URL` | No | Redis URL for checkpointing (default: `redis://localhost:6379/0`) |

## Branches

| Branch | Purpose |
|--------|---------|
| `main` | Implementation code + documentation |
| `planning` | Extended planning docs and weekly visualizations |
