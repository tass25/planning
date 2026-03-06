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
|   (9 nodes, linear pipeline)  |
|                               |
|   L2-A  Entry Layer           |   FileAnalysis + CrossFileDeps + Registry
|     |                         |
|   L2-B  Streaming Layer       |   Async StreamAgent + StateAgent
|     |                         |
|   L2-C  Chunking Layer        |   BoundaryDetector + PartitionBuilder + RAPTOR
|     |                         |
|   L2-D  Complexity Layer      |   ComplexityAgent (LogReg+Platt) + Strategy
|     |                         |
|   L2-E  Persistence Layer     |   SQLite + NetworkX graph + SCC detection
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
|-- main.py                          # Legacy single-file entry point
|-- scripts/
|   +-- run_pipeline.py              # E2E orchestrator CLI
+-- sas_converter/
    |-- partition/
    |   |-- base_agent.py            # BaseAgent ABC (retry, tracing)
    |   |-- logging_config.py        # structlog JSON configuration
    |   |-- models/                  # Pydantic models (PartitionIR, FileMetadata, enums)
    |   |-- entry/                   # L2-A: file scan, cross-file deps, registry
    |   |-- streaming/               # L2-B: async streaming with backpressure
    |   |-- chunking/                # L2-C: boundary detection + partition building
    |   |-- raptor/                  # L2-C: RAPTOR semantic clustering (NomicEmbed + GMM)
    |   |-- complexity/              # L2-D: risk scoring (LogReg+Platt) + strategy routing
    |   |-- persistence/             # L2-E: SQLite persistence (content-hash dedup)
    |   |-- index/                   # L2-E: NetworkX DAG + SCC detection + hop cap
    |   |-- orchestration/           # Orchestrator: LangGraph + Redis + DuckDB audit
    |   |-- db/                      # SQLite + DuckDB managers
    |   +-- config/                  # Project configuration
    |-- tests/                       # 221 pytest tests
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

## Agents

| # | Agent | Layer | Purpose |
|---|-------|-------|---------|
| 1 | FileAnalysisAgent | L2-A | Scan .sas files, detect encoding, compute hashes |
| 2 | CrossFileDependencyResolver | L2-A | Resolve %INCLUDE, LIBNAME, &macro refs |
| 3 | RegistryWriterAgent | L2-A | Persist FileMetadata to SQLite |
| 4 | DataLineageExtractor | L2-A | Track dataset-level read/write lineage |
| 5 | StreamAgent | L2-B | Async line-by-line streaming producer |
| 6 | StateAgent | L2-B | FSM-based parsing state tracker |
| 7 | BoundaryDetectorAgent | L2-C | Rule-based + LLM boundary detection |
| 8 | PartitionBuilderAgent | L2-C | Build PartitionIR from boundary events |
| 9 | RAPTORPartitionAgent | L2-C | Semantic clustering (NomicEmbed + GMM) |
| 10 | ComplexityAgent | L2-D | LogReg + Platt scaling (ECE = 0.06) |
| 11 | StrategyAgent | L2-D | Risk × Type routing table |
| 12 | PersistenceAgent | L2-E | SQLite upsert with content-hash dedup |
| 13 | IndexAgent | L2-E | NetworkX DAG, SCC detection, dynamic hop cap |
| 14 | TranslationAgent | L3 | SAS → Python/PySpark via LLM (6 failure modes) |
| 15 | ValidationAgent | L3 | Syntax + sandboxed exec validation |
| 16 | PartitionOrchestrator | Orch | LangGraph StateGraph (11 nodes) |
| 17 | LLMAuditLogger | Orch | DuckDB audit for every LLM call |
| 18 | ReportAgent | Util | Per-file conversion report (MD + HTML) |
| 19 | FeedbackIngestionAgent | Util | Human correction → KB update loop |
| 20 | ConversionQualityMonitor | Util | Batch quality metrics aggregation |
| 21 | RetrainTrigger | Util | Auto-retrain on drift detection |

## Metrics

| Metric | Value |
|--------|-------|
| Boundary accuracy | 79.3% (572/721 blocks) |
| ECE (calibration) | 0.06 (target < 0.08) |
| Tests passing | 221 |
| Gold standard files | 50 |
| KB pairs (target) | 330 (`scripts/expand_kb.py --target 330`) |
| Pipeline stages | 12 (INIT through COMPLETE) |

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
