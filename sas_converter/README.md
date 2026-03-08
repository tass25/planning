# SAS Converter -- RAPTOR v2

![CI](https://github.com/<YOUR_GITHUB_USERNAME>/sas-converter/actions/workflows/ci.yml/badge.svg)

Multi-agent SAS-to-Python/PySpark conversion accelerator using LangGraph orchestration, RAPTOR semantic clustering, and Azure OpenAI inference.

## Architecture

```
Input: SAS file(s) / directory
         |
         v
+-------------------------------+
|   PartitionOrchestrator #15   |   LangGraph StateGraph
|   (8 nodes, linear pipeline)  |
|                               |
|   L2-A  Entry Layer           |   FileProcessor (scan + deps + registry)
|     |                         |
|   L2-B  Streaming Layer       |   StreamingParser (async stream + FSM)
|     |                         |
|   L2-C  Chunking Layer        |   ChunkingAgent + RAPTORPartitionAgent
|     |                         |
|   L2-D  Complexity Layer      |   RiskRouter (LogReg+Platt + Strategy)
|     |                         |
|   L2-E  Persistence Layer     |   PersistenceAgent + IndexAgent (SQLite + DAG)
|     |                         |
|   L3   Translation Layer      |   TranslationPipeline (translate + validate)
|     |                         |
|   L4   Merge Layer            |   MergeAgent (assemble scripts + reports)
|                               |
+-------------------------------+
         |
   Redis Checkpoints (every 50 blocks, TTL 24h)
   DuckDB Audit Logs (every LLM call)
   Azure OpenAI (GPT-4o-mini / GPT-4o tiered routing)
```

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Orchestration | LangGraph StateGraph | Pipeline DAG with typed state |
| LLM Inference | Azure OpenAI (GPT-4o-mini, GPT-4o) | Boundary resolution, summarization |
| Embeddings | Nomic Embed v1.5 | RAPTOR semantic clustering |
| Vector Store | LanceDB | Embedding persistence |
| Relational DB | SQLite (WAL mode) | File registry, partitions, lineage |
| Analytics DB | DuckDB | LLM audit logs, calibration, metrics |
| Graph DB | NetworkX | Dependency DAG, SCC detection |
| Checkpointing | Redis | Fault-tolerant resume (degraded mode) |
| ML | scikit-learn | LogReg + Platt scaling (ECE < 0.08) |
| Telemetry | Azure Monitor + App Insights | Production observability |
| CI/CD | GitHub Actions | Automated testing on push |

## Setup

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1                               # Windows

pip install -r sas_converter/requirements.txt
```

### Azure OpenAI Configuration

```bash
$env:AZURE_OPENAI_API_KEY = "your-key"
$env:AZURE_OPENAI_ENDPOINT = "https://your-resource.openai.azure.com/"
$env:AZURE_OPENAI_API_VERSION = "2024-10-21"
$env:AZURE_OPENAI_DEPLOYMENT_MINI = "gpt-4o-mini"        # LOW/MODERATE risk
$env:AZURE_OPENAI_DEPLOYMENT_FULL = "gpt-4o"              # HIGH risk
```

## Quick Start

```bash
# Full E2E pipeline via orchestrator
python scripts/run_pipeline.py data/sas_files/ --target python

# Legacy single-file mode
python main.py --file path/to/file.sas

# Demo (no API key needed, deterministic only)
cd sas_converter
$env:PYTHONPATH = "$PWD"
../venv/Scripts/python examples/demo_pipeline.py
```

## Project Structure

```
Stage/
|-- main.py                          # DEPRECATED — use run_pipeline.py
|-- scripts/
|   +-- run_pipeline.py              # ★ Primary CLI entry point
+-- sas_converter/
    |-- partition/
    |   |-- base_agent.py            # BaseAgent ABC (retry, tracing)
    |   |-- logging_config.py        # structlog JSON configuration
    |   |-- models/                  # Pydantic models (PartitionIR, FileMetadata, enums)
    |   |-- entry/                   # L2-A: FileProcessor (scan + deps + registry)
    |   |-- streaming/               # L2-B: StreamingParser (async stream + FSM)
    |   |-- chunking/                # L2-C: ChunkingAgent (boundary + partition)
    |   |-- raptor/                  # L2-C: RAPTOR semantic clustering (NomicEmbed + GMM)
    |   |-- complexity/              # L2-D: RiskRouter (LogReg+Platt + strategy)
    |   |-- persistence/             # L2-E: SQLite persistence (content-hash dedup)
    |   |-- index/                   # L2-E: NetworkX DAG + SCC detection + hop cap
    |   |-- translation/             # L3: TranslationPipeline (LLM + validation)
    |   |-- merge/                   # L4: MergeAgent (script assembly + reports)
    |   |-- orchestration/           # Orchestrator: LangGraph + Redis + DuckDB audit
    |   |-- db/                      # SQLite + DuckDB managers
    |   +-- config/                  # Project configuration
    |-- tests/                       # 200+ pytest tests
    |-- benchmark/                   # 721-block accuracy benchmark (79.3%)
    |-- knowledge_base/
    |   +-- gold_standard/           # 50 .sas + 50 .gold.json (3 tiers)
    |-- examples/                    # Demo pipeline + sample SAS file
    +-- requirements.txt
```

## Gold Standard Corpus

| Tier | Files | Blocks | Description |
|------|-------|--------|-------------|
| Simple (gs_) | 15 | ~350 | Single block type, minimal nesting |
| Medium (gsm_) | 20 | ~220 | Mixed types, macro calls, workflows |
| Hard (gsh_) | 15 | ~151 | Enterprise ETL, nested macros, cross-file |
| **Total** | **50** | **721** | |

## Agents (Consolidated — 8 Agents, 8 Pipeline Nodes)

| # | Agent | Layer | Purpose |
|---|-------|-------|---------|
| 1 | FileProcessor | L2-A | Scan .sas files, resolve cross-file deps, write to SQLite registry |
| 2 | StreamingParser | L2-B | Async line-by-line streaming + FSM state tracking |
| 3 | ChunkingAgent | L2-C | Rule-based + LLM boundary detection, partition building |
| 4 | RAPTORPartitionAgent | L2-C | Semantic clustering (NomicEmbed + GMM) |
| 5 | RiskRouter | L2-D | LogReg + Platt scaling (ECE = 0.06) + strategy routing |
| 6 | PersistenceAgent + IndexAgent | L2-E | SQLite upsert + NetworkX DAG + SCC detection |
| 7 | TranslationPipeline | L3 | SAS → Python/PySpark via LLM (6 failure modes) + validation |
| 8 | MergeAgent | L4 | Import consolidation + script assembly + conversion reports |

## Metrics

| Metric | Value |
|--------|-------|
| Boundary accuracy | 79.3% (572/721 blocks) |
| ECE (calibration) | 0.06 (target < 0.08) |
| Tests passing | 200+ |
| Gold standard files | 50 |
| KB pairs (target) | 330 (`scripts/expand_kb.py --target 330`) |
| Pipeline nodes | 8 (file_process → merge → END) |

> **Boundary accuracy gap note:** The cahier des charges targets 90% boundary
> accuracy. The current 79.3% reflects a 50-file gold corpus; accuracy improves
> as more gold annotations are added. LLM-resolved boundaries carry inherent
> variance across prompt versions and model updates. ECE = 0.06 confirms the
> model is well-calibrated, so the confidence scores are trustworthy even where
> boundaries disagree with gold labels.

## Running Tests

```bash
cd sas_converter
$env:PYTHONPATH = "$PWD"
../venv/Scripts/python -m pytest tests/ -v
```

## Branches

| Branch | Purpose |
|--------|---------|
| `main` | Implementation code only |
| `planning` | Planning docs, visualizations, debug scripts, weekXDone.md |
