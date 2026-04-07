# SAS → Python/PySpark Conversion Accelerator — Global Reference Document

> **Version**: 3.0.0 (post-consolidation)
> **Project Type**: PFE (Projet de Fin d'Études) — Final-year engineering internship
> **Duration**: 14 weeks (Feb 2026 – May 2026)
> **Methodology**: Hybrid Kanban + Weekly Sprints
> **Grade**: A- (Production-ready MVP)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Statement & Motivation](#2-problem-statement--motivation)
3. [Architecture Overview](#3-architecture-overview)
4. [Pipeline Flow (8 Nodes)](#4-pipeline-flow-8-nodes)
5. [Agent Catalog (8 Agents)](#5-agent-catalog-8-agents)
6. [Data Models & Schemas](#6-data-models--schemas)
7. [Technology Stack](#7-technology-stack)
8. [Database Architecture](#8-database-architecture)
9. [RAG Sub-System (3 Paradigms)](#9-rag-sub-system-3-paradigms)
10. [RAPTOR Semantic Clustering](#10-raptor-semantic-clustering)
11. [Orchestration & LangGraph](#11-orchestration--langgraph)
12. [Knowledge Base System](#12-knowledge-base-system)
13. [Evaluation & Metrics](#13-evaluation--metrics)
14. [Gold Standard Corpus](#14-gold-standard-corpus)
15. [Security & Enterprise Features](#15-security--enterprise-features)
16. [DevOps & CI/CD](#16-devops--cicd)
17. [Project Structure (File Tree)](#17-project-structure-file-tree)
18. [UML Diagrams](#18-uml-diagrams)
19. [14-Week Planning Timeline](#19-14-week-planning-timeline)
20. [Week-by-Week Deliverables Summary](#20-week-by-week-deliverables-summary)
21. [Test Suite](#21-test-suite)
22. [Scripts & CLI Tools](#22-scripts--cli-tools)
23. [Dependencies (requirements.txt)](#23-dependencies-requirementstxt)
24. [Configuration Reference](#24-configuration-reference)
25. [Known Limitations & Future Work](#25-known-limitations--future-work)
26. [Glossary](#26-glossary)

---

## 1. Project Overview

**SAS → Python/PySpark Conversion Accelerator** is a multi-agent, LLM-orchestrated pipeline that automates the translation of legacy SAS code into modern Python/PySpark. It uses:

- **8 consolidated agents** (down from 21 pre-consolidation)
- **LangGraph StateGraph** as the orchestration backbone
- **RAPTOR hierarchical clustering** (Sarthi et al., ICLR 2024) for semantic code understanding
- **3 RAG paradigms** (Static, Graph, Agentic) for intelligent knowledge retrieval
- A **721-block gold standard corpus** spanning 50 annotated SAS files across 3 complexity tiers

The system processes SAS files through 8 sequential stages: scanning → streaming → chunking → RAPTOR clustering → risk routing → persistence/indexing → translation → merge, producing validated Python scripts with comprehensive reports.

---

## 2. Problem Statement & Motivation

### Why This Project Exists

Enterprises running legacy SAS codebases face:
1. **High licensing costs** — SAS licenses are expensive
2. **Talent scarcity** — Fewer new developers learn SAS
3. **Migration pressure** — Regulatory and business need to move to open-source stacks
4. **Manual conversion risk** — Hand-translating thousands of SAS programs is error-prone and slow

### 6 Identified Failure Modes in SAS→Python Translation

| # | Failure Mode | SAS Construct | Why It's Hard |
|---|-------------|---------------|---------------|
| 1 | **DATE_ARITHMETIC** | SAS date values (days since 1960-01-01) | Different epoch, different format codes |
| 2 | **MERGE_LOGIC** | `MERGE` with `BY` + `IN=` flags, FIRST./LAST. | Complex join semantics with no direct pandas equivalent |
| 3 | **RETAIN_STATE** | `RETAIN` statement in DATA step | Stateful row-by-row processing, alien to pandas vectorization |
| 4 | **MACRO_EXPANSION** | `%MACRO`, `%LET`, nested `%DO` | Text substitution engine with no Python parallel |
| 5 | **PROC_SQL_DIALECT** | PROC SQL with SAS-specific functions | SAS SQL extensions not in standard SQL |
| 6 | **FORMAT_INFORMATS** | `FORMAT`, `INFORMAT`, `PUT()`, `INPUT()` | 100+ proprietary format codes with no standard mapping |

---

## 3. Architecture Overview

### Layered Architecture (4 Layers)

```
┌─────────────────────────────────────────────────────┐
│                   Layer 4 (L4)                      │
│              MergeAgent + ReportAgent                │
│         Script assembly · Import dedup · Reports     │
├─────────────────────────────────────────────────────┤
│                   Layer 3 (L3)                      │
│             TranslationPipeline                      │
│     3 RAG paradigms · 6 failure modes · Sandbox     │
├─────────────────────────────────────────────────────┤
│                   Layer 2 (L2)                      │
│  ┌──────┐ ┌────────┐ ┌────────┐ ┌──────┐ ┌──────┐ │
│  │L2-A  │→│ L2-B   │→│ L2-C   │→│L2-D  │→│L2-E  │ │
│  │Entry │ │Stream  │ │Chunk + │ │Risk  │ │Persist│ │
│  │Scan  │ │Parse   │ │RAPTOR  │ │Route │ │Index  │ │
│  └──────┘ └────────┘ └────────┘ └──────┘ └──────┘ │
├─────────────────────────────────────────────────────┤
│              Infrastructure Layer                    │
│   SQLite · DuckDB · LanceDB · Redis · NetworkX      │
│   structlog · OpenTelemetry · Azure Monitor          │
└─────────────────────────────────────────────────────┘
```

---

## 4. Pipeline Flow (8 Nodes)

### LangGraph StateGraph (v3.0.0)

```
START
  │
  ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ 1. file_     │───►│ 2. streaming │───►│ 3. chunking  │
│    process   │    │              │    │              │
│ FileProcessor│    │StreamingParser│   │ChunkingAgent │
└──────────────┘    └──────────────┘    └──────────────┘
                                              │
  ┌───────────────────────────────────────────┘
  ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ 4. raptor    │───►│ 5. risk_     │───►│ 6. persist_  │
│              │    │    routing   │    │    index     │
│RAPTORPartition│   │ RiskRouter   │    │Persist+Index │
│    Agent     │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
                                              │
  ┌───────────────────────────────────────────┘
  ▼
┌──────────────┐    ┌──────────────┐
│ 7. translate │───►│ 8. merge     │───► END
│              │    │              │
│Translation   │    │ MergeAgent   │
│Pipeline      │    │              │
└──────────────┘    └──────────────┘
```

### State Object (PipelineState TypedDict)

Every node receives and returns partial updates to this shared state:

```python
class PipelineState(TypedDict):
    # Input
    input_paths: list[str]           # SAS file paths
    target_runtime: str              # "python" | "pyspark"

    # Current stage
    stage: str                       # PipelineStage enum value
    current_file_idx: int

    # L2-A outputs
    file_metas: list                 # FileMetadata objects
    file_ids: list[str]              # UUIDs from registry
    cross_file_deps: dict            # {ref_raw: target_file_id}

    # L2-B/C outputs
    chunks_by_file: dict             # {file_id: [(LineChunk, ParsingState)]}
    partitions: list                 # PartitionIR objects
    partition_count: int

    # RAPTOR outputs
    raptor_nodes: list               # RAPTORNode objects

    # L2-D outputs
    complexity_computed: bool

    # L2-E outputs
    persisted_count: int
    scc_groups: list                 # SCC group sets
    max_hop: int                     # Dynamic hop cap

    # L3 outputs
    conversion_results: list         # ConversionResult objects
    validation_passed: int

    # L4 outputs
    merge_results: list              # Per-file merged outputs
    errors: list[str]
    warnings: list[str]
```

---

## 5. Agent Catalog (8 Agents)

All agents inherit from `BaseAgent` ABC which provides:
- `trace_id: UUID` — unique per pipeline invocation
- `logger` — structlog bound with `agent=name, trace_id=id`
- `@with_retry` — exponential backoff decorator (max_retries=3, base_delay=1s)
- Abstract `async process()` method

### Agent #1: FileProcessor (L2-A)

| Property | Value |
|----------|-------|
| **File** | `partition/entry/file_processor.py` |
| **Consolidates** | FileAnalysisAgent + CrossFileDependencyResolver + RegistryWriterAgent + DataLineageExtractor |
| **Input** | Directory path or list of `.sas` file paths |
| **Output** | `list[FileMetadata]`, populated `file_registry`, `cross_file_deps`, `data_lineage` DB tables |
| **Key Tech** | `chardet` (encoding detection), SHA-256 (dedup), Lark LALR (pre-validation), SQLAlchemy |

**Sub-components:**
- **FileAnalysisAgent** — Recursively discovers `.sas` files, detects encoding (UTF-8/Latin-1/Windows-1252), computes SHA-256 content hash, counts lines, runs Lark pre-validation
- **CrossFileDependencyResolver** — Regex-parses `%INCLUDE` and `LIBNAME` statements, builds directed dependency adjacency dict, detects circular includes
- **RegistryWriterAgent** — Persists `FileMetadata` to SQLite `file_registry` table with upsert (INSERT OR IGNORE on content_hash)
- **DataLineageExtractor** — Parses `DATA`/`SET`/`MERGE`/`UPDATE` statements and `PROC` step `DATA=` options to extract TABLE_READ/TABLE_WRITE edges

### Agent #2: StreamingParser (L2-B)

| Property | Value |
|----------|-------|
| **File** | `partition/streaming/streaming_parser.py` |
| **Consolidates** | StreamAgent + StateAgent |
| **Input** | File content (string or path) |
| **Output** | `list[tuple[LineChunk, ParsingState]]` |
| **Key Tech** | `aiofiles` (async I/O), `asyncio.Queue` (backpressure), FSM state machine |

**Sub-components:**
- **StreamAgent** — Async producer: reads file line-by-line using `aiofiles`, pushes `LineChunk` objects to a bounded `asyncio.Queue` (backpressure based on file size)
- **StateAgent** — Async consumer: FSM parser tracking `block_type`, `nesting_depth`, `macro_stack`, emitting structured parsing states
- **Pipeline** — `run_streaming_pipeline()` orchestrates producer/consumer with timeout

**Performance targets:** 10K-line file < 2s, < 100 MB peak memory

### Agent #3: ChunkingAgent (L2-C)

| Property | Value |
|----------|-------|
| **File** | `partition/chunking/chunking_agent.py` |
| **Consolidates** | BoundaryDetectorAgent + PartitionBuilderAgent |
| **Input** | `list[tuple[LineChunk, ParsingState]]` |
| **Output** | `list[PartitionIR]` |
| **Key Tech** | Rules engine + Ollama `llama3.1:8b` (via `instructor`), Lark LALR grammar |

**Sub-components:**
- **BoundaryDetectorAgent** — 3-tier detection: (1) deterministic rules for clear patterns (`DATA`, `PROC`, `%MACRO`), (2) ambiguous pattern matcher, (3) LLM resolver (Ollama llama3.1:8b) for remaining ambiguities
- **LLMBoundaryResolver** — Sends ambiguous code snippets to local Ollama with structured output via `instructor`
- **PartitionBuilderAgent** — Converts `BlockBoundaryEvent` stream into `PartitionIR` objects with contiguous line ranges

**Benchmark:** 79.3% boundary accuracy on 721-block gold standard (572/721 correct)

### Agent #4: RAPTORPartitionAgent (L2-C)

| Property | Value |
|----------|-------|
| **File** | `partition/raptor/raptor_agent.py` |
| **Input** | `list[PartitionIR]` |
| **Output** | `list[RAPTORNode]` + back-linked partitions |
| **Key Tech** | Nomic Embed v1.5 (768-dim), GMM (BIC minimization), Groq llama-3.3-70b, LanceDB |

**Sub-components:**
- **NomicEmbedder** — Local sentence-transformers model (`nomic-ai/nomic-embed-text-v1.5`, 768-dim, Apache 2.0 license)
- **GMMClusterer** — Gaussian Mixture Model with BIC-based K selection, threshold τ=0.72
- **ClusterSummarizer** — Groq LLM (llama-3.3-70b-versatile) generates natural language summaries per cluster, cached
- **RAPTORTreeBuilder** — Recursive tree: leaf nodes (level 0) → cluster summaries (level 1-3) → root, depth 3-5
- **LanceDBWriter** — Stores all RAPTORNode embeddings in LanceDB with IVF index (cosine, 32-64 partitions)

### Agent #5: RiskRouter (L2-D)

| Property | Value |
|----------|-------|
| **File** | `partition/complexity/risk_router.py` |
| **Consolidates** | ComplexityAgent + StrategyAgent |
| **Input** | `list[PartitionIR]` |
| **Output** | Annotated partitions (risk_level, strategy, complexity_score, calibration_confidence) |
| **Key Tech** | scikit-learn LogReg + Platt scaling |

**Sub-components:**
- **ComplexityAgent** — Extracts 5 features per block:
  1. **Cyclomatic Complexity (CC)** — Control flow branches
  2. **Nesting Depth** — Max `%DO`/`IF` nesting
  3. **Macro Density** — Ratio of macro constructs to total lines
  4. **Dependency Count** — Number of cross-block/cross-file refs
  5. **SQL Complexity** — Subqueries, joins, CTEs in PROC SQL
- **StrategyAgent** — Logistic Regression classifier with Platt scaling for calibrated confidence scores
  - Routes to: `FLAT_PARTITION`, `MACRO_AWARE`, `DEPENDENCY_PRESERVING`, `STRUCTURAL_GROUPING`, `HUMAN_REVIEW`
  - ECE (Expected Calibration Error) = 0.06 (target: < 0.08)

### Agent #6: PersistenceAgent + IndexAgent (L2-E)

| Property | Value |
|----------|-------|
| **Files** | `partition/persistence/persistence_agent.py`, `partition/index/index_agent.py` |
| **Input** | Annotated `list[PartitionIR]` |
| **Output** | Persisted rows in SQLite, NetworkX DAG, SCC groups |
| **Key Tech** | SQLite WAL, Parquet (for 10K+ partitions), NetworkX |

**Sub-components:**
- **PersistenceAgent** — SQLite INSERT OR IGNORE for deduplication; switches to Parquet for files with 10K+ partitions
- **IndexAgent** — Builds a NetworkX directed graph from partition dependencies:
  - SCC condensation (Tarjan's algorithm) to detect circular dependency groups
  - Dynamic hop cap to limit graph traversal depth
  - Powers the Graph RAG paradigm's context retrieval

### Agent #7: TranslationPipeline (L3)

| Property | Value |
|----------|-------|
| **File** | `partition/translation/translation_pipeline.py` |
| **Input** | Persisted partitions + KB + RAPTOR tree |
| **Output** | `list[ConversionResult]` |
| **Key Tech** | Azure GPT-4o (full/mini), Groq fallback, exec() sandbox |

**Sub-components:**
- **TranslationAgent** — Performs SAS→Python translation using one of 3 RAG paradigms (selected by risk + dependency profile):
  - Static RAG (k=3), Graph RAG (k=5 + graph context), Agentic RAG (adaptive k, retry, level escalation)
  - Uses Azure GPT-4o-mini for LOW risk, GPT-4o-full for MODERATE/HIGH, Groq as fallback
- **ValidationAgent** — Executes translated Python in a hardened sandbox:
  - `exec()` with blocked dangerous builtins (`open`, `eval`, `exec`, `__import__`, `compile`, etc.)
  - 100-row synthetic DataFrame for functional testing
  - 5-second timeout per execution
  - Retries up to 3 times on validation failure
- **FailureModeDetector** — Detects which of the 6 failure modes applies, guides KB retrieval
- **KBQueryClient** — LanceDB retrieval with partition_type and failure_mode filters

### Agent #8: MergeAgent (L4)

| Property | Value |
|----------|-------|
| **File** | `partition/merge/merge_agent.py` |
| **Input** | `list[ConversionResult]` grouped by source file |
| **Output** | `list[MergedScript]`, Markdown + HTML reports |
| **Key Tech** | `ast.parse()`, ImportConsolidator, CodeBLEU scoring |

**Sub-components:**
- **ScriptMerger** — Merges translated blocks ordered by `line_start`, validates final script with `ast.parse()`
- **ImportConsolidator** — Deduplicates imports, sorts PEP 8 style (stdlib → 3rd-party → local)
- **DependencyInjector** — Replaces SAS references with snake_case Python equivalents
- **ReportAgent** — Generates comprehensive Markdown + HTML conversion reports with:
  - Summary stats (total/success/partial/failed/human_review)
  - Failure mode breakdown
  - CodeBLEU scores
  - Validation results per block
  - Dependency graph statistics
  - KB retrieval statistics

---

## 6. Data Models & Schemas

### 6.1 FileMetadata (Pydantic v2)

```python
class FileMetadata(BaseModel):
    file_id: UUID = Field(default_factory=uuid4)
    file_path: str                    # Path to .sas file
    encoding: str                     # 'utf-8', 'ISO-8859-1', etc.
    content_hash: str                 # SHA-256 hex digest
    file_size_bytes: int
    line_count: int
    lark_valid: bool                  # Lark pre-validation passed?
    lark_errors: list[str] = []
    created_at: datetime
```

### 6.2 PartitionIR (Pydantic v2)

```python
class PartitionIR(BaseModel):
    block_id: UUID = Field(default_factory=uuid4)
    file_id: UUID                     # FK to FileMetadata
    partition_type: PartitionType     # One of 10 enum values
    source_code: str                  # Raw SAS code for this block
    line_start: int                   # 1-based
    line_end: int                     # 1-based
    risk_level: RiskLevel = UNCERTAIN
    conversion_status: ConversionStatus = HUMAN_REVIEW
    dependencies: list[UUID] = []     # Block IDs this depends on
    metadata: dict[str, Any] = {}

    # RAPTOR back-links
    raptor_leaf_id: str | None
    raptor_cluster_id: str | None
    raptor_root_id: str | None
```

### 6.3 RAPTORNode (Pydantic v2)

```python
class RAPTORNode(BaseModel):
    node_id: str
    level: int                        # 0=leaf, 1-3=cluster, 4+=root
    embedding: list[float]            # 768-dim Nomic Embed
    summary: str                      # LLM-generated cluster summary
    child_ids: list[str] = []
    partition_ids: list[UUID] = []    # Leaf-level back-refs
```

### 6.4 ConversionResult

```python
class ConversionResult(BaseModel):
    conversion_id: UUID
    partition_id: UUID                # FK to PartitionIR
    python_code: str
    status: ConversionStatus
    confidence: float
    validation_passed: bool
    error_log: str = ""
    llm_model: str
    retry_count: int = 0
```

### 6.5 Enums

```python
class PartitionType(str, Enum):
    DATA_STEP = "DATA_STEP"
    PROC_BLOCK = "PROC_BLOCK"
    MACRO_DEFINITION = "MACRO_DEFINITION"
    MACRO_INVOCATION = "MACRO_INVOCATION"
    SQL_BLOCK = "SQL_BLOCK"
    CONDITIONAL_BLOCK = "CONDITIONAL_BLOCK"
    LOOP_BLOCK = "LOOP_BLOCK"
    GLOBAL_STATEMENT = "GLOBAL_STATEMENT"
    INCLUDE_REFERENCE = "INCLUDE_REFERENCE"
    UNCLASSIFIED = "UNCLASSIFIED"

class RiskLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    UNCERTAIN = "UNCERTAIN"

class ConversionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    HUMAN_REVIEW = "HUMAN_REVIEW"

class PartitionStrategy(str, Enum):
    FLAT_PARTITION = "FLAT_PARTITION"
    MACRO_AWARE = "MACRO_AWARE"
    DEPENDENCY_PRESERVING = "DEPENDENCY_PRESERVING"
    STRUCTURAL_GROUPING = "STRUCTURAL_GROUPING"
    HUMAN_REVIEW = "HUMAN_REVIEW"
```

---

## 7. Technology Stack

### Core Framework

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| **Orchestration** | LangGraph StateGraph | ≥ 0.2 | 8-node pipeline graph, state management |
| **LLM Inference** | Azure OpenAI (GPT-4o) | API 2024-10-21 | Translation (tiered: mini for LOW, full for MOD/HIGH) |
| **LLM Fallback** | Groq | ≥ 0.25 | llama-3.3-70b-versatile, RAPTOR summarization |
| **LLM Boundary** | Ollama | local | llama3.1:8b, boundary disambiguation |
| **Embeddings** | Nomic Embed v1.5 | 768-dim | Local, Apache 2.0, sentence-transformers |
| **Structured Output** | instructor | ≥ 1.8 | Structured LLM responses |

### Data & Storage

| Category | Technology | Purpose |
|----------|-----------|---------|
| **Relational DB** | SQLite (WAL mode) | 7 tables: file registry, deps, lineage, partitions, conversions, merged scripts, schema version |
| **Analytics DB** | DuckDB | 7 columnar tables: LLM audit, calibration, ablation, quality, feedback, KB changelog, conversion reports |
| **Vector DB** | LanceDB | IVF index (cosine, 32-64 partitions), RAPTOR nodes + KB pairs |
| **Graph DB** | NetworkX | DAG + SCC detection + multi-hop traversal |
| **Checkpoint** | Redis | Every 50 blocks, TTL 24h, graceful degraded mode |

### ML & Processing

| Category | Technology | Purpose |
|----------|-----------|---------|
| **ML Models** | scikit-learn | LogReg + Platt scaling (ECE=0.06) |
| **Math** | NumPy | Array ops, embedding math |
| **Parsing** | Lark | LALR grammar for SAS pre-validation |
| **Encoding** | chardet | Automatic encoding detection |
| **Async I/O** | aiofiles | Streaming file reads |
| **Serialization** | Pydantic v2 | Runtime schema validation |
| **ORM** | SQLAlchemy 2.0 | SQLite ORM + WAL pragma |
| **Columnar** | PyArrow | Parquet fallback for 10K+ partition files |

### Telemetry & DevOps

| Category | Technology | Purpose |
|----------|-----------|---------|
| **Logging** | structlog | Structured JSON/console logging |
| **Tracing** | OpenTelemetry | Distributed tracing (trace_event, trace_span) |
| **Monitoring** | Azure Monitor | Cloud telemetry integration |
| **CI/CD** | GitHub Actions | Tests + CodeQL + Dependabot |
| **Container** | Docker (multi-stage) | Python 3.11-slim, non-root user |
| **Compose** | docker-compose 3.9 | Redis + Pipeline services |
| **Templates** | Jinja2 | Prompt template management |
| **Markdown** | markdown2 | HTML report generation |

---

## 8. Database Architecture

### 8.1 SQLite Database (`file_registry.db`) — 7 Tables

```
┌─────────────────────────────────────────────────────────────┐
│                       file_registry                         │
│ file_id (PK) │ file_path │ encoding │ content_hash (UNIQUE) │
│ file_size_bytes │ line_count │ lark_valid │ lark_errors      │
│ status │ error_log │ created_at                              │
└─────────┬───────────────────────────────────────────────────┘
          │ FK
┌─────────▼───────────────────────────────────────────────────┐
│                     cross_file_deps                         │
│ id (PK, auto) │ source_file_id (FK) │ ref_type              │
│ raw_reference │ resolved │ target_file_id (FK) │ target_path │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      data_lineage                           │
│ id (PK, auto) │ source_file_id (FK) │ lineage_type          │
│ source_dataset │ target_dataset │ source_columns (JSON)      │
│ target_column │ transform_expr │ block_line_start/end        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      partition_ir                           │
│ partition_id (PK) │ source_file_id (FK) │ partition_type     │
│ risk_level │ conversion_status │ content_hash                │
│ complexity_score │ calibration_confidence │ strategy          │
│ line_start │ line_end │ control_depth │ has_macros            │
│ has_nested_sql │ raw_code │ raptor_leaf/cluster/root_id      │
│ scc_id │ created_at                                          │
└─────────┬───────────────────────────────────────────────────┘
          │ FK
┌─────────▼───────────────────────────────────────────────────┐
│                   conversion_results                        │
│ conversion_id (PK) │ partition_id (FK) │ target_lang         │
│ translated_code │ validation_status │ error_log              │
│ llm_model │ llm_tier │ retry_count │ created_at              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     merged_scripts                          │
│ script_id (PK) │ source_file_id (FK) │ output_path           │
│ n_blocks │ status │ created_at                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    schema_version                           │
│ version (INT) │ applied_at (TEXT)                            │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 DuckDB Analytics Database (`analytics.duckdb`) — 7 Tables

```
llm_audit              → Every LLM call (agent, model, latency_ms, tokens, success)
calibration_log        → ECE per training run (ece_score, n_samples, model_version)
ablation_results       → RAPTOR vs flat (hit_at_5, reciprocal_rank, complexity_tier)
quality_metrics        → Per-batch quality (success_rate, failure_mode_dist JSON)
feedback_log           → Correction tracking (correction_source, accepted, rejection_reason)
kb_changelog           → KB versioning (action, old_version, new_version, diff_summary)
conversion_reports     → Per-file reports (codebleu_mean, report_md_path)
```

### 8.3 LanceDB Vector Database

```
raptor_nodes           → All RAPTOR tree nodes (node_id, level, embedding[768], summary, child_ids)
sas_python_examples    → 330+ KB pairs (sas_code, python_code, embedding[768], partition_type,
                          complexity_tier, verified, failure_mode, version, category)
                        → IVF index (64 partitions, cosine metric) auto-built at 128+ rows
```

### 8.4 NetworkX Graph (`partition_graph.gpickle`)

```
Nodes: partition_id (one per PartitionIR)
Edges: dependency relationships (cross-block, cross-file)
SCC Condensation: Tarjan's algorithm groups circular deps
Hop Cap: Dynamic (max_hop from config, default 10)
```

---

## 9. RAG Sub-System (3 Paradigms)

The RAG router (`partition/rag/router.py`) selects the paradigm based on risk level and dependency count:

```
┌──────────────────────────────────────────────────────────┐
│                    RAG Paradigm Router                     │
│                                                           │
│  if risk == LOW and deps < 3:     → Static RAG            │
│  if risk == MODERATE or deps >= 3: → Graph RAG            │
│  if risk == HIGH:                  → Agentic RAG          │
└──────────────────────────────────────────────────────────┘
```

### Static RAG
- **k = 3** fixed retrieval from LanceDB
- **Filter**: `partition_type` match
- Best for: Simple blocks with no cross-dependencies
- File: `partition/rag/static_rag.py`

### Graph RAG
- **k = 5** retrieval + NetworkX graph context
- Includes: Adjacent partition code via SCC groups + hop traversal
- Best for: Blocks with moderate cross-file or cross-block dependencies
- File: `partition/rag/graph_rag.py`

### Agentic RAG
- **Adaptive k** (starts at 3, escalates to 10)
- **Retrieval retry**: If first retrieval confidence < threshold, re-queries with refined filters
- **Level escalation**: Traverses RAPTOR tree upward for broader context
- Best for: Complex enterprise blocks (macros, nested SQL, CALL EXECUTE)
- File: `partition/rag/agentic_rag.py`

---

## 10. RAPTOR Semantic Clustering

Based on **Sarthi et al., "Raptor: Recursive Abstractive Processing for Tree-Organized Retrieval" (ICLR 2024)**.

### Process Flow

```
PartitionIR blocks
       │
       ▼
┌──────────────┐
│ 1. Embed     │  Nomic Embed v1.5 (768-dim, local)
│              │  Input: source_code of each partition
└──────┬───────┘
       ▼
┌──────────────┐
│ 2. Cluster   │  GMM (Gaussian Mixture Model)
│              │  - BIC minimization for optimal K
│              │  - Soft assignment threshold τ = 0.72
│              │  - A partition can belong to multiple clusters
└──────┬───────┘
       ▼
┌──────────────┐
│ 3. Summarize │  Groq llama-3.3-70b-versatile
│              │  - One summary per cluster
│              │  - Cached to avoid re-generation
└──────┬───────┘
       ▼
┌──────────────┐
│ 4. Build Tree│  Recursive: Level 0 (leaves) → Level 1-3 (clusters) → Root
│              │  - Re-embed summaries → re-cluster → re-summarize
│              │  - Max depth: 3-5 levels
│              │  - Back-link: partition.raptor_leaf_id → tree nodes
└──────┬───────┘
       ▼
┌──────────────┐
│ 5. Store     │  LanceDB IVF index (cosine, 32-64 partitions)
│              │  - All nodes: leaf + cluster + root
│              │  - Enables multi-level retrieval for RAG
└──────────────┘
```

### Key Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Embedding model | nomic-ai/nomic-embed-text-v1.5 | Local, 768-dim, Apache 2.0, competitive with OpenAI ada-002 |
| Embedding dim | 768 | Balance between quality and memory |
| Clustering | GMM with BIC | Auto-selects K without manual tuning |
| τ (cluster threshold) | 0.72 | Soft assignment: blocks can belong to multiple clusters |
| Max tree depth | 3-5 | Diminishing returns beyond 5 levels |
| Summarizer | Groq llama-3.3-70b | Fast, free tier, good summarization quality |
| LanceDB index | IVF, cosine | Built at 128+ rows, 32-64 partitions for fast retrieval |

---

## 11. Orchestration & LangGraph

### LangGraph StateGraph Construction

```python
graph = StateGraph(PipelineState)
graph.add_node("file_process", self._node_file_process)
graph.add_node("streaming", self._node_streaming)
graph.add_node("chunking", self._node_chunking)
graph.add_node("raptor", self._node_raptor)
graph.add_node("risk_routing", self._node_risk_routing)
graph.add_node("persist_index", self._node_persist_index)
graph.add_node("translation", self._node_translation)
graph.add_node("merge", self._node_merge)

graph.set_entry_point("file_process")
graph.add_edge("file_process", "streaming")
graph.add_edge("streaming", "chunking")
graph.add_edge("chunking", "raptor")
graph.add_edge("raptor", "risk_routing")
graph.add_edge("risk_routing", "persist_index")
graph.add_edge("persist_index", "translation")
graph.add_edge("translation", "merge")
graph.add_edge("merge", END)
```

### Redis Checkpointing

- **Frequency**: Every 50 blocks processed
- **TTL**: 24 hours
- **Degraded mode**: If Redis is unavailable, pipeline continues without checkpointing (logs warning)
- **Recovery**: On restart, loads last checkpoint from Redis and resumes from that stage

### DuckDB Audit Logging

Every LLM call is logged to DuckDB `llm_audit` table:
```
(call_id, agent_name, model_name, prompt_hash, response_hash,
 latency_ms, success, error_msg, tier, timestamp)
```

### Telemetry (OpenTelemetry + Azure Monitor)

- `track_event(name, properties)` — Custom events
- `track_metric(name, value, unit)` — Numeric metrics
- `trace_span(name)` — Context manager for distributed tracing

---

## 12. Knowledge Base System

### Structure

The KB stores verified SAS↔Python translation pairs in LanceDB table `sas_python_examples`:

| Field | Type | Description |
|-------|------|-------------|
| example_id | str | Unique identifier |
| sas_code | str | Original SAS code snippet |
| python_code | str | Verified Python translation |
| embedding | float[768] | Nomic Embed vector of SAS code |
| partition_type | str | e.g. "DATA_STEP", "PROC_BLOCK" |
| complexity_tier | str | "simple", "medium", "hard" |
| target_runtime | str | "python" or "pyspark" |
| verified | bool | Cross-verified by dual LLM |
| source | str | "generated" or "human" |
| failure_mode | str | One of 6 failure modes or "NONE" |
| verification_method | str | "dual_llm" or "human_review" |
| verification_score | float | 0.0-1.0 confidence |
| category | str | One of 15 canonical categories |
| version | int | Version number (for rollback) |
| superseded_by | str | ID of newer version (if superseded) |
| created_at | str | ISO 8601 timestamp |

### Generation Pipeline

```
generate_kb_pairs.py
       │
       ▼
┌──────────────────┐     ┌──────────────────┐
│ Azure GPT-4o     │────►│ Groq llama-3.3   │
│ (Generator)      │     │ (Cross-verifier) │
│ Generate SAS↔Py  │     │ Verify correctness│
│ 15 categories    │     │ confidence ≥ 0.85 │
└──────────────────┘     └──────┬───────────┘
                                │
                                ▼
                     ┌──────────────────┐
                     │ LanceDB INSERT   │
                     │ sas_python_examples│
                     │ IVF index rebuild │
                     └──────────────────┘
```

### 15 KB Categories

1. DATA_STEP_BASIC, 2. DATA_STEP_RETAIN, 3. DATA_STEP_MERGE, 4. DATA_STEP_ARRAY,
5. PROC_MEANS, 6. PROC_FREQ, 7. PROC_SORT, 8. PROC_REG, 9. PROC_SQL_BASIC,
10. PROC_SQL_JOIN, 11. MACRO_SIMPLE, 12. MACRO_NESTED, 13. CONDITIONAL,
14. LOOP, 15. GLOBAL_STATEMENT

### Continuous Learning Loop

```
ConversionQualityMonitor
       │ Rolling 100 results
       │
       ▼
  success_rate < 0.70?  ──yes──► RetrainingTrigger
  KB < 500 pairs?       ──yes──► │
  ECE > 0.12?           ──yes──► │
                                  │
                                  ▼
                        ┌──────────────────┐
                        │ FeedbackIngestion │
                        │ Agent            │
                        │ CLI corrections + │
                        │ automated sources │
                        └──────────────────┘
```

---

## 13. Evaluation & Metrics

### Key Metrics

| Metric | Target | Achieved | Method |
|--------|--------|----------|--------|
| **Boundary Accuracy** | 90% | **79.3%** (572/721) | Gold standard comparison with TOLERANCE=2 |
| **ECE (Calibration)** | < 0.08 | **0.06** | LogReg + Platt scaling on held-out 20% |
| **Tests Passing** | > 95% | **97.7%** (216/221) | pytest (2 pre-existing async, 3 skipped) |
| **RAPTOR Hit-Rate@5** | ≥ 0.82 | Pending | Ablation: RAPTOR vs flat on 500 files × 10 queries |
| **CodeBLEU** | ≥ 0.55 | Pending | Translation quality metric |
| **Streaming Throughput** | 50K lines/s | Pending | 10K-line benchmark |
| **KB Pairs** | 330 | **330+** | Dual-LLM generated + verified |
| **Agent Count** | ≤ 10 | **8** | Post-consolidation (was 21) |

### Ablation Study Design

Compares RAPTOR hierarchical retrieval vs flat baseline:
- **500 files × 10 queries** = 5,000 retrieval operations
- Measures: Hit-Rate@5, Reciprocal Rank, Query Latency
- Segmented by complexity tier (simple/medium/hard)
- Results stored in DuckDB `ablation_results` table

### Boundary Accuracy Benchmark

```python
# Tolerance-based matching (TOLERANCE=2 lines)
def is_match(detected, gold):
    return (abs(detected.line_start - gold.line_start) <= 2
            and abs(detected.line_end - gold.line_end) <= 2)
```

---

## 14. Gold Standard Corpus

### Overview

50 manually annotated SAS files with 721 block boundaries across 3 tiers.

### Tier Breakdown

| Tier | Prefix | Files | Blocks | Lines | Characteristics |
|------|--------|-------|--------|-------|-----------------|
| **Simple** | `gs_*` | 15 | ~350 | 7-50 | Single block type, minimal nesting, clean boundaries |
| **Medium** | `gsm_*` | 20 | ~220 | 100-250 | Mixed types (3-6), macro calls, ETL workflows |
| **Hard** | `gsh_*` | 15 | ~151 | 400+ | Enterprise: nested macros, cross-file includes, CALL EXECUTE |
| **Total** | | **50** | **721** | | |

### Annotation Format (`.gold.json`)

```json
{
  "file": "gs_01_basic_data_step.sas",
  "tier": "simple",
  "blocks": [
    {
      "block_type": "DATA_STEP",
      "line_start": 1,
      "line_end": 8,
      "test_coverage_type": "full",
      "data_lineage": ["src.sales", "work.active"]
    }
  ]
}
```

### Block Type Distribution

| Block Type | Count | Examples |
|-----------|-------|---------|
| DATA_STEP | 60+ | RETAIN, MERGE, FIRST/LAST, arrays |
| PROC_BLOCK | 50+ | MEANS, FREQ, SORT, REG, SQL |
| SQL_BLOCK | 25+ | Subqueries, joins, CTEs |
| MACRO_DEFINITION | 25+ | %MACRO/%MEND |
| MACRO_INVOCATION | 20+ | %macro_name() calls |
| CONDITIONAL_BLOCK | 15+ | %IF/%THEN |
| LOOP_BLOCK | 15+ | %DO/%END |
| GLOBAL_STATEMENT | 25+ | OPTIONS, LIBNAME, TITLE |
| INCLUDE_REFERENCE | 10+ | %INCLUDE |

### File List (50 files)

**Simple tier (gs_*):** gs_01_basic_data_step, gs_02_retain_accumulator, gs_03_merge_bygroup, gs_04_first_last, gs_05_etl_pipeline, gs_07_multi_output, gs_08_hash_lookup, gs_11_proc_means, gs_12_proc_freq, gs_21_sql_simple, gs_22_sql_joins, gs_26_macro_basic, gs_37_do_loop_list, gs_42_include_refs, gs_43_filename_libname

**Medium tier (gsm_*):** gsm_01 through gsm_20 (financial_summary, customer_segmentation, claims_processing, inventory_analysis, employee_report, survey_analysis, time_series, data_cleaning, cohort_analysis, marketing_roi, risk_scoring, supply_chain, sales_dashboard, compliance_check, ab_testing, data_reconciliation, etl_incremental, macro_reporting, longitudinal, audit_trail)

**Hard tier (gsh_*):** gsh_01 through gsh_15 (enterprise_etl, macro_framework, warehouse_load, clinical_trial, fraud_detection, regulatory_report, migration_suite, batch_processor, analytics_pipeline, financial_recon, scoring_engine, data_governance, portfolio_analysis, multi_source_merge, complete_report)

---

## 15. Security & Enterprise Features

### Security Measures

| Feature | Implementation |
|---------|----------------|
| **Hardened exec() sandbox** | Blocked builtins: `open`, `eval`, `exec`, `__import__`, `compile`, `globals`, `locals`, `getattr`, `setattr`, `delattr` |
| **SHA-256 pickle integrity** | Graph pickle files verified before loading |
| **Path traversal guards** | `Path.is_relative_to()` checks on all file operations |
| **SQL injection protection** | SQLAlchemy ORM with parameterized queries (no raw SQL with user input) |
| **No hardcoded secrets** | All API keys via environment variables (`.env` file, never committed) |
| **Non-root Docker** | Container runs as `appuser`, not root |
| **Execution timeout** | 5-second timeout on sandbox exec() |
| **WAL mode** | SQLite WAL journal for crash safety |

### Observability Stack

```
┌────────────┐    ┌──────────────┐    ┌──────────────┐
│ structlog  │───►│ console/JSON │    │ Azure Monitor│
│ (logging)  │    │ + rotating   │    │ (cloud)      │
│            │    │ file (10MB×5)│    │              │
└────────────┘    └──────────────┘    └──────────────┘
       │
       ▼
┌────────────┐    ┌──────────────┐
│OpenTelemetry│──►│ trace_event  │
│ (tracing)   │   │ trace_span   │
│             │   │ track_metric │
└─────────────┘   └──────────────┘
       │
       ▼
┌────────────────┐
│ DuckDB llm_audit│
│ (every LLM call)│
└────────────────┘
```

---

## 16. DevOps & CI/CD

### Docker Multi-Stage Build

```dockerfile
# Stage 1: Builder (gcc/g++ for native deps)
FROM python:3.11-slim AS builder
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime (slim, non-root)
FROM python:3.11-slim
COPY --from=builder /install /usr/local
COPY sas_converter/ ./sas_converter/
RUN useradd --create-home appuser
USER appuser
CMD ["python", "scripts/run_pipeline.py", "--help"]
```

### Docker Compose

```yaml
services:
  redis:          # Redis 7 Alpine (checkpoint store)
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck: redis-cli ping

  pipeline:       # Main application
    build: .
    env_file: .env
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis: { condition: service_healthy }
```

### GitHub Actions CI

- **Test suite**: `pytest` on every push/PR
- **CodeQL**: Static security analysis
- **Dependabot**: Automated dependency updates
- **Branch strategy**: `week-XX` branches merged to `main` weekly

---

## 17. Project Structure (File Tree)

```
sas_converter/
├── partition/
│   ├── __init__.py
│   ├── base_agent.py                    # BaseAgent ABC (@with_retry, trace_id, logger)
│   ├── logging_config.py               # structlog setup (console/JSON, RotatingFileHandler)
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── enums.py                    # PartitionType(10), RiskLevel(4), ConversionStatus(4), PartitionStrategy(5)
│   │   ├── partition_ir.py             # PartitionIR Pydantic v2 model
│   │   ├── file_metadata.py            # FileMetadata Pydantic v2 model
│   │   ├── raptor_node.py              # RAPTORNode Pydantic v2 model
│   │   └── conversion_result.py        # ConversionResult Pydantic v2 model
│   │
│   ├── entry/                          # L2-A: File ingestion
│   │   ├── __init__.py
│   │   ├── file_processor.py           # FileProcessor (consolidated)
│   │   ├── file_analysis_agent.py      # Scan, encoding, hash, Lark validate
│   │   ├── cross_file_dep_resolver.py  # %INCLUDE, LIBNAME parsing
│   │   ├── registry_writer_agent.py    # SQLite upsert
│   │   └── data_lineage_extractor.py   # TABLE_READ/WRITE extraction
│   │
│   ├── streaming/                      # L2-B: Async streaming
│   │   ├── __init__.py
│   │   ├── streaming_parser.py         # StreamingParser (consolidated)
│   │   ├── stream_agent.py             # Async aiofiles producer
│   │   ├── state_agent.py              # FSM consumer
│   │   ├── pipeline.py                 # Producer/consumer orchestration
│   │   ├── models.py                   # LineChunk, ParsingState
│   │   └── backpressure.py             # Queue sizing
│   │
│   ├── chunking/                       # L2-C: Boundary detection
│   │   ├── __init__.py
│   │   ├── chunking_agent.py           # ChunkingAgent (consolidated)
│   │   ├── boundary_detector.py        # 3-tier detection
│   │   ├── llm_boundary_resolver.py    # Ollama llama3.1:8b
│   │   ├── partition_builder.py        # Event → PartitionIR
│   │   └── models.py                   # BlockBoundaryEvent
│   │
│   ├── raptor/                         # L2-C: RAPTOR clustering
│   │   ├── __init__.py
│   │   ├── raptor_agent.py             # RAPTORPartitionAgent
│   │   ├── embedder.py                 # NomicEmbedder (768-dim)
│   │   ├── clustering.py               # GMMClusterer (BIC)
│   │   ├── summarizer.py               # Groq 70b summarization
│   │   ├── tree_builder.py             # Recursive tree (depth 3-5)
│   │   └── lancedb_writer.py           # LanceDB IVF index
│   │
│   ├── complexity/                     # L2-D: Risk assessment
│   │   ├── __init__.py
│   │   ├── risk_router.py              # RiskRouter (consolidated)
│   │   ├── complexity_agent.py         # 5 feature extraction
│   │   ├── strategy_agent.py           # LogReg + Platt (ECE=0.06)
│   │   └── features.py                # Feature utilities
│   │
│   ├── persistence/                    # L2-E: Persistence
│   │   ├── __init__.py
│   │   └── persistence_agent.py        # SQLite + Parquet fallback
│   │
│   ├── index/                          # L2-E: Graph indexing
│   │   ├── __init__.py
│   │   ├── index_agent.py              # NetworkX DAG + SCC
│   │   └── graph_builder.py            # DiGraph construction
│   │
│   ├── translation/                    # L3: Code translation
│   │   ├── __init__.py
│   │   ├── translation_pipeline.py     # TranslationPipeline
│   │   ├── translation_agent.py        # 3 RAG paradigms
│   │   ├── validation_agent.py         # Sandbox exec() validation
│   │   ├── kb_query.py                 # LanceDB retrieval
│   │   └── failure_mode_detector.py    # 6 failure modes
│   │
│   ├── merge/                          # L4: Assembly & reporting
│   │   ├── __init__.py
│   │   ├── merge_agent.py              # MergeAgent (consolidated)
│   │   ├── script_merger.py            # Block ordering + ast.parse()
│   │   ├── import_consolidator.py      # PEP 8 import ordering
│   │   ├── dependency_injector.py      # SAS→Python ref replacement
│   │   └── report_agent.py             # Markdown + HTML reports
│   │
│   ├── rag/                            # RAG paradigm router
│   │   ├── __init__.py
│   │   ├── router.py                   # Paradigm selection
│   │   ├── static_rag.py              # k=3 fixed
│   │   ├── graph_rag.py               # k=5 + NetworkX
│   │   └── agentic_rag.py             # Adaptive k, retry, escalation
│   │
│   ├── orchestration/                  # Pipeline orchestration
│   │   ├── __init__.py
│   │   ├── orchestrator.py             # LangGraph 8-node graph
│   │   ├── state.py                    # PipelineState TypedDict
│   │   ├── checkpoint.py               # Redis checkpointing
│   │   ├── audit.py                    # DuckDB LLM audit logging
│   │   └── telemetry.py               # OpenTelemetry integration
│   │
│   ├── db/                             # Database managers
│   │   ├── __init__.py
│   │   ├── sqlite_manager.py           # 7 ORM models + engine setup
│   │   └── duckdb_manager.py           # 7 analytics tables
│   │
│   ├── kb/                             # Knowledge base
│   │   ├── __init__.py
│   │   ├── kb_writer.py                # LanceDB insert + versioning
│   │   └── kb_changelog.py             # Mutation tracking
│   │
│   ├── retraining/                     # Continuous learning
│   │   ├── __init__.py
│   │   ├── feedback_ingestion.py       # CLI corrections + auto sources
│   │   ├── quality_monitor.py          # Rolling 100 success rate
│   │   └── retrain_trigger.py          # Drift detection triggers
│   │
│   ├── evaluation/                     # Ablation & evaluation
│   │   ├── __init__.py
│   │   ├── ablation_runner.py          # RAPTOR vs flat (500×10)
│   │   ├── flat_index.py               # Flat retrieval baseline
│   │   └── query_generator.py          # Test query generation
│   │
│   ├── utils/                          # Shared utilities
│   │   ├── __init__.py
│   │   ├── llm_clients.py             # LLM factory (Azure, Groq)
│   │   ├── retry.py                    # @with_retry, circuit breaker
│   │   └── large_file.py              # Memory guards (CUDA, OMP)
│   │
│   ├── config/                         # Configuration
│   │   ├── __init__.py
│   │   └── config_manager.py           # YAML loader + env overrides
│   │
│   └── prompts/                        # Prompt templates
│       ├── __init__.py
│       └── manager.py                  # Jinja2 template management
│
├── tests/                              # Test suite (216/221 passing)
│   ├── __init__.py
│   ├── test_file_analysis.py           # 25 tests
│   ├── test_streaming.py               # 22 tests
│   ├── test_boundary_detector.py       # 20 tests
│   ├── test_complexity_agent.py        # 18 tests
│   ├── test_strategy_agent.py          # 15 tests
│   ├── test_raptor.py                  # 15 tests
│   ├── test_persistence.py             # 12 tests
│   ├── test_translation.py             # 25 tests
│   ├── test_merge_retraining.py        # 18 tests
│   ├── test_integration.py             # 30+ tests
│   ├── test_rag.py
│   ├── test_evaluation.py
│   ├── test_robustness_kb.py
│   ├── test_orchestration.py
│   ├── test_data_lineage.py
│   ├── test_cross_file_deps.py
│   ├── test_registry_writer.py
│   └── regression/
│       └── test_boundary_accuracy.py   # CI guard ≥ 79.3%
│
├── knowledge_base/
│   └── gold_standard/                  # 50 .sas + 50 .gold.json files
│
├── benchmark/
│   ├── __init__.py
│   └── boundary_benchmark.py           # Gold standard benchmark
│
├── scripts/
│   ├── generate_kb_pairs.py            # Dual-LLM KB generation
│   ├── expand_kb.py                    # Expand to 330 pairs
│   ├── init_ablation_db.py             # Initialize ablation.db
│   ├── analyze_ablation.py             # Plot ablation results
│   ├── kb_rollback.py                  # Version rollback
│   └── submit_correction.py            # CLI correction submission
│
├── examples/
│   ├── demo_pipeline.py                # Demo (deterministic, no LLM)
│   ├── test_input.sas                  # 36-line sample SAS
│   └── README.md
│
├── config/
│   └── project_config.yaml             # Master configuration
│
├── docs/
│   ├── AUDIT_REPORT.md                 # 150-item comprehensive audit
│   └── AUDIT_REPORT_V2.md              # Follow-up audit
│
├── logs/                               # Rotating log files
├── lancedb_data/                       # LanceDB storage
├── requirements.txt
└── README.md

# Root-level files
├── main.py                             # Legacy CLI (L2-A/B/C only)
├── conftest.py                         # pytest configuration
├── pyproject.toml                      # Project metadata
├── docker-compose.yml                  # Redis + Pipeline services
├── Dockerfile                          # Multi-stage build
├── analytics.duckdb                    # DuckDB analytics database
├── partition_graph.gpickle             # NetworkX dependency graph
└── scripts/
    └── run_pipeline.py                 # Primary CLI orchestrator
```

---

## 18. UML Diagrams

### 18.1 Class Diagram — Agent Hierarchy

```
┌───────────────────────────────────────────┐
│              <<abstract>>                 │
│              BaseAgent                    │
├───────────────────────────────────────────┤
│ + trace_id: UUID                          │
│ + logger: structlog.Logger                │
├───────────────────────────────────────────┤
│ + agent_name: str {abstract}              │
│ + process(*args, **kwargs) {abstract}     │
└───────────────┬───────────────────────────┘
                │ inherits
    ┌───────────┼────────────┬──────────────┬──────────────┐
    │           │            │              │              │
    ▼           ▼            ▼              ▼              ▼
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐
│File     │ │Streaming│ │Chunking │ │RAPTOR    │ │Risk      │
│Processor│ │Parser   │ │Agent    │ │Partition │ │Router    │
│         │ │         │ │         │ │Agent     │ │          │
└─────────┘ └─────────┘ └─────────┘ └──────────┘ └──────────┘

    ┌───────────┬───────────────┐
    │           │               │
    ▼           ▼               ▼
┌──────────┐ ┌───────────┐ ┌──────────┐
│Persistence│ │Translation│ │Merge     │
│Agent +   │ │Pipeline   │ │Agent     │
│IndexAgent│ │           │ │          │
└──────────┘ └───────────┘ └──────────┘
```

### 18.2 Sequence Diagram — Full Pipeline Execution

```
User            Orchestrator     FileProc    Stream    Chunk     RAPTOR    Risk     Persist   Translate   Merge
  │                  │              │          │         │         │        │          │          │          │
  │──run(paths)──►   │              │          │         │         │        │          │          │          │
  │                  │──process()──►│          │         │         │        │          │          │          │
  │                  │              │──scan──► │         │         │        │          │          │          │
  │                  │              │◄─metas── │         │         │        │          │          │          │
  │                  │              │──deps──► │         │         │        │          │          │          │
  │                  │              │◄─graph── │         │         │        │          │          │          │
  │                  │◄─file_ids───│          │         │         │        │          │          │          │
  │                  │                        │         │         │        │          │          │          │
  │                  │──process()────────────►│         │         │        │          │          │          │
  │                  │                        │──parse─►│         │        │          │          │          │
  │                  │◄─chunks────────────────│         │         │        │          │          │          │
  │                  │                                  │         │        │          │          │          │
  │                  │──process()───────────────────────►│        │        │          │          │          │
  │                  │                                  │──detect►│        │          │          │          │
  │                  │◄─partitions──────────────────────│        │        │          │          │          │
  │                  │                                           │        │          │          │          │
  │                  │──process()────────────────────────────────►│       │          │          │          │
  │                  │                                           │──embed►│          │          │          │
  │                  │                                           │──GMM──►│          │          │          │
  │                  │                                           │──tree─►│          │          │          │
  │                  │◄─raptor_nodes─────────────────────────────│       │          │          │          │
  │                  │                                                   │          │          │          │
  │                  │──process()────────────────────────────────────────►│         │          │          │
  │                  │                                                   │──score──►│          │          │
  │                  │◄─risk_levels──────────────────────────────────────│         │          │          │
  │                  │                                                             │          │          │
  │                  │──process()─────────────────────────────────────────────────►│          │          │
  │                  │                                                             │──SQLite─►│          │
  │                  │                                                             │──DAG───►│          │
  │                  │◄─persisted_count/scc_groups────────────────────────────────│          │          │
  │                  │                                                                       │          │
  │                  │──process()───────────────────────────────────────────────────────────►│          │
  │                  │                                                                       │──RAG───►│
  │                  │                                                                       │──LLM───►│
  │                  │                                                                       │──valid─►│
  │                  │◄─conversion_results──────────────────────────────────────────────────│          │
  │                  │                                                                                  │
  │                  │──process()──────────────────────────────────────────────────────────────────────►│
  │                  │                                                                                  │──merge──►
  │                  │                                                                                  │──report─►
  │                  │◄─merge_results/reports───────────────────────────────────────────────────────────│
  │◄─PipelineState──│
  │                  │
```

### 18.3 Component Diagram — Data Flow

```
                                    ┌─────────────┐
                                    │  .sas Files  │
                                    └──────┬──────┘
                                           │
                                    ┌──────▼──────┐
                                    │ FileProcessor│
                                    │   (L2-A)    │
                                    └──┬───┬───┬──┘
                                       │   │   │
                          ┌────────────┘   │   └────────────┐
                          ▼                ▼                ▼
                    ┌──────────┐    ┌──────────┐    ┌──────────┐
                    │ SQLite   │    │ StreamParse│   │ DuckDB   │
                    │file_reg  │    │  (L2-B)   │    │ audit    │
                    │deps/lin  │    └─────┬─────┘    └──────────┘
                    └──────────┘          │
                                   ┌─────▼─────┐
                                   │ Chunking   │
                                   │  (L2-C)    │
                                   └─────┬─────┘
                                         │
                              ┌──────────┼──────────┐
                              ▼                     ▼
                       ┌──────────┐          ┌──────────┐
                       │  RAPTOR  │          │RiskRouter │
                       │  (L2-C)  │          │  (L2-D)   │
                       └────┬─────┘          └─────┬────┘
                            │                      │
                            ▼                      │
                       ┌──────────┐                │
                       │ LanceDB  │                │
                       │raptor_nodes│               │
                       └──────────┘                │
                                                   ▼
                                            ┌──────────┐
                                            │ Persist  │
                                            │ + Index  │
                                            │  (L2-E)  │
                                            └────┬─────┘
                                                 │
                                    ┌────────────┼────────────┐
                                    ▼            ▼            ▼
                             ┌──────────┐ ┌──────────┐ ┌──────────┐
                             │ SQLite   │ │ NetworkX │ │ LanceDB  │
                             │partition │ │  DAG     │ │ KB pairs │
                             │_ir      │ │ + SCC    │ │          │
                             └──────────┘ └──────────┘ └─────┬────┘
                                                             │
                                                      ┌──────▼──────┐
                                                      │ Translation │
                                                      │   (L3)      │
                                                      │ 3 RAG modes │
                                                      └──────┬──────┘
                                                             │
                                                      ┌──────▼──────┐
                                                      │  Merge      │
                                                      │  (L4)       │
                                                      └──────┬──────┘
                                                             │
                                                ┌────────────┼────────────┐
                                                ▼            ▼            ▼
                                          ┌──────────┐ ┌──────────┐ ┌──────────┐
                                          │ .py files│ │ MD/HTML  │ │ DuckDB   │
                                          │ (output) │ │ reports  │ │ quality  │
                                          └──────────┘ └──────────┘ └──────────┘
```

### 18.4 State Machine Diagram — StreamAgent FSM

```
                ┌─────────┐
                │  IDLE   │
                └────┬────┘
                     │ read line
                     ▼
              ┌──────────────┐
              │ CLASSIFY_LINE│◄──────────────────────────┐
              └──────┬───────┘                           │
                     │                                   │
        ┌────────────┼────────────┬──────────┐          │
        ▼            ▼            ▼          ▼          │
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────┐    │
   │DATA_STEP│ │PROC_BLOCK│ │MACRO_DEF│ │SQL_BLOCK│   │
   │         │ │          │ │         │ │        │    │
   │depth++  │ │depth++   │ │depth++  │ │depth++ │    │
   └────┬────┘ └────┬─────┘ └────┬────┘ └───┬────┘    │
        │           │            │           │          │
        └───────────┴────────────┴───────────┘          │
                     │ RUN;/QUIT;/%MEND                 │
                     │ depth-- → 0                      │
                     ▼                                   │
              ┌──────────────┐                          │
              │ EMIT_BOUNDARY│──────────────────────────┘
              └──────────────┘
```

### 18.5 Entity Relationship Diagram — Database

```
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│ file_registry │◄───FK──│cross_file_deps│        │ data_lineage │
│              │        │              │        │              │
│ file_id (PK) │        │ id (PK)      │        │ id (PK)      │
│ file_path    │        │ source_file_id│◄───FK──│source_file_id│
│ encoding     │        │ ref_type     │        │ lineage_type │
│ content_hash │        │ raw_reference│        │ source_dataset│
│ file_size    │        │ resolved     │        │ target_dataset│
│ line_count   │        │ target_file_id│       │ source_columns│
│ lark_valid   │        │ target_path  │        │ block_line_*  │
│ created_at   │        └──────────────┘        └──────────────┘
└──────┬───────┘
       │ FK
┌──────▼───────┐        ┌──────────────┐
│ partition_ir │◄───FK──│conversion_   │
│              │        │results       │
│ partition_id │        │              │
│ source_file_id│       │ conversion_id│
│ partition_type│       │ partition_id │
│ risk_level   │        │ target_lang  │
│ complexity   │        │ translated_  │
│ strategy     │        │   code       │
│ line_start   │        │ validation   │
│ line_end     │        │ llm_model    │
│ raw_code     │        │ retry_count  │
│ raptor_*_id  │        └──────────────┘
│ scc_id       │
└──────┬───────┘
       │ FK
┌──────▼───────┐
│merged_scripts│
│              │
│ script_id    │
│ source_file_id│
│ output_path  │
│ n_blocks     │
│ status       │
└──────────────┘
```

### 18.6 Deployment Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose Host                       │
│                                                             │
│  ┌────────────────────┐    ┌──────────────────────────────┐│
│  │   Redis Container   │    │      Pipeline Container      ││
│  │   redis:7-alpine    │    │      python:3.11-slim        ││
│  │                     │    │                              ││
│  │  ┌──────────────┐  │    │  ┌─────────────────────┐    ││
│  │  │ Checkpoint   │◄─┼────┼──│ PartitionOrchestrator│    ││
│  │  │ Store        │  │    │  │ (8 agents)           │    ││
│  │  │ TTL: 24h     │  │    │  └──────────┬──────────┘    ││
│  │  └──────────────┘  │    │             │                ││
│  │                     │    │  ┌──────────▼──────────┐    ││
│  │  Port: 6379         │    │  │    Local Storage     │    ││
│  └────────────────────┘    │  │                      │    ││
│                             │  │  ├── file_registry.db│   ││
│                             │  │  ├── analytics.duckdb│   ││
│  ┌────────────────────┐    │  │  ├── lancedb_data/   │    ││
│  │  External APIs      │    │  │  ├── partition_graph │    ││
│  │                     │    │  │  └── output/*.py     │    ││
│  │  ├── Azure OpenAI   │◄───┼──│                      │    ││
│  │  ├── Groq Cloud     │    │  └─────────────────────┘    ││
│  │  └── Ollama (local) │    │                              ││
│  └────────────────────┘    │  User: appuser (non-root)    ││
│                             └──────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## 19. 14-Week Planning Timeline

| Week | Layer | Deliverable | Priority | Key Agents | Success Gate |
|------|-------|-------------|----------|------------|--------------|
| **1-2** | L2-A | Entry + CrossFileDeps + DataLineage + Gold Standard (50 files, 721 blocks) | **P0** | FileAnalysis, CrossFileDep, RegistryWriter, DataLineage | 50 files scanned, DB tables populated, gold corpus annotated |
| **2-3** | L2-B | StreamAgent + StateAgent | **P0** | StreamAgent, StateAgent | 10K-line < 2s, < 100 MB memory |
| **3-4** | L2-C | BoundaryDetector + LLM resolver | **P0** | BoundaryDetectorAgent | 721-block benchmark > 90% accuracy |
| **4** | L2-D | ComplexityAgent + StrategyAgent | **P0** | ComplexityAgent, StrategyAgent | ECE < 0.08 on held-out 20% |
| **5-6** | L2-C | RAPTOR: Nomic Embed + GMM + Summarizer + TreeBuilder | **P1** | RAPTORPartitionAgent | BIC convergence, clusters formed |
| **7** | L2-E | Persistence + NetworkX DAG + SCC + DuckDB schemas | **P1** | PersistenceAgent, IndexAgent | All schemas created, SCC ≥ 90% |
| **8** | Orch | LangGraph orchestration + Redis + audit logging | **P1** | PartitionOrchestrator | Full L2 pipeline end-to-end |
| **9** | Robust | Robustness + large file strategy + KB gen start | **P2** | — | 250 KB pairs, large-file fallback |
| **10** | L3 | TranslationAgent + ValidationAgent | **P2** | TranslationAgent, ValidationAgent | Translation ≥ 70%, validation gate |
| **11** | L4+CL | Merge + Report + Continuous Learning + KB to 330 | **P2** | MergeAgent, FeedbackIngestion | ≥ 95% syntax valid |
| **12** | Eval | Ablation study: RAPTOR vs flat | **P2** | — | RAPTOR hit-rate@5 > 0.82 |
| **13** | Consol | Agent consolidation (21→8) + Enterprise features | **P3** | — | 8 agents, 200 tests pass, v3.0.0 |
| **14** | Buffer | Defense slides + polish + README | **P3** | — | All docs finalized |

---

## 20. Week-by-Week Deliverables Summary

### Week 1-2: L2-A Entry & Scan + Gold Standard ✅

**Deliverables:**
- Project scaffold (directory structure, venv, base classes)
- `BaseAgent` ABC with `@with_retry`, `trace_id`, structlog logger
- `PartitionType` enum (10 values), `RiskLevel`, `ConversionStatus`, `PartitionStrategy`
- `FileMetadata` and `PartitionIR` Pydantic v2 models
- `FileAnalysisAgent` — scan `.sas` files, detect encoding, compute SHA-256 hash, count lines, Lark validate
- `CrossFileDependencyResolver` — parse `%INCLUDE`/`LIBNAME`, build dependency graph, detect circular includes
- `RegistryWriterAgent` — SQLite upsert to `file_registry` table
- `DataLineageExtractor` — extract TABLE_READ/TABLE_WRITE edges from DATA/PROC steps
- SQLite database schema (3 tables: `file_registry`, `cross_file_deps`, `data_lineage`)
- 50-file gold standard corpus (15 simple + 20 medium + 15 hard = 721 blocks)
- 15 unit tests (all passing)
- ~875 lines of production code

**Errors encountered:**
1. `line_end` off-by-one in gold JSONs (fixed with TOLERANCE=2)
2. `PROC_SQL` type annotation error (fixed with regex replace across 50 files)
3. `asyncio.get_event_loop()` deprecation (replaced with `asyncio.run()`)
4. Missing `from __future__ import annotations` (added to all modules)
5. Hard-tier corpus underrepresented (created gsh_01 through gsh_15)

### Week 2-3: L2-B Streaming Core ✅

**Deliverables:**
- `StreamAgent` — async line reader with `aiofiles` + bounded queue
- `StateAgent` — FSM parser tracking block type, nesting depth, macro stack
- `run_streaming_pipeline()` — producer/consumer orchestration
- `LineChunk` and `ParsingState` models
- Backpressure queue sizing based on file size
- 22 tests (throughput, memory, FSM accuracy)

### Week 3-4: L2-C Boundary Detection ✅

**Deliverables:**
- `BoundaryDetectorAgent` — 3-tier detection (rules → ambiguous → LLM)
- `LLMBoundaryResolver` — Ollama llama3.1:8b with instructor
- `PartitionBuilderAgent` — events → PartitionIR conversion
- 721-block benchmark: **79.3% accuracy** (572/721)
- 20 tests

### Week 4: L2-D Complexity & Strategy ✅

**Deliverables:**
- `ComplexityAgent` — 5 feature extraction
- `StrategyAgent` — LogReg + Platt scaling, **ECE = 0.06**
- 5 partition strategies routed by risk level
- 18 + 15 tests

### Week 5-6: RAPTOR Semantic Clustering ✅

**Deliverables:**
- `NomicEmbedder` — 768-dim local embeddings
- `GMMClusterer` — BIC-based K selection (τ=0.72)
- `ClusterSummarizer` — Groq llama-3.3-70b
- `RAPTORTreeBuilder` — recursive depth 3-5
- `LanceDBWriter` — IVF cosine index
- 15 tests

### Week 7: Persistence & Indexing ✅

**Deliverables:**
- `PersistenceAgent` — SQLite + Parquet for 10K+
- `IndexAgent` — NetworkX DAG + SCC condensation
- `DuckDB` schema (7 analytics tables)
- `partition_ir`, `conversion_results`, `merged_scripts` tables
- 12 tests

### Week 8: Orchestration ✅

**Deliverables:**
- `PartitionOrchestrator` — LangGraph 8-node StateGraph
- `PipelineState` TypedDict
- `RedisCheckpointManager` — every 50 blocks, degraded mode
- `LLMAuditLogger` — DuckDB logging
- OpenTelemetry integration
- 30+ integration tests

### Week 9: Robustness + KB ✅

**Deliverables:**
- `generate_kb_pairs.py` — dual-LLM chain (Azure + Groq cross-verify)
- `expand_kb.py` — category-aware expansion to 330 pairs
- Large file handling (memory guards, 500MB+ fallback)
- `@with_retry` + circuit breaker
- 250+ KB pairs generated

### Week 10: Translation & Validation ✅

**Deliverables:**
- `TranslationAgent` — 3 RAG paradigms
- `ValidationAgent` — hardened exec() sandbox
- `FailureModeDetector` — 6 failure modes
- `KBQueryClient` — LanceDB retrieval with filters
- 25 tests

### Week 11: Merge + Continuous Learning ✅

**Deliverables:**
- `MergeAgent` — script assembly + reporting
- `ScriptMerger` — block ordering + `ast.parse()` gate
- `ImportConsolidator` — PEP 8 import dedup
- `ReportAgent` — Markdown + HTML conversion reports
- `FeedbackIngestionAgent` + `ConversionQualityMonitor` + `RetrainingTrigger`
- KB expanded to 330+ pairs
- 18 tests

### Week 12: Ablation Study ✅

**Deliverables:**
- `ablation_runner.py` — RAPTOR vs flat (500×10)
- `flat_index.py` — flat retrieval baseline
- `init_ablation_db.py` — DuckDB ablation tables
- `analyze_ablation.py` — results analysis + plotting

### Week 13: Consolidation & Enterprise ✅

**Deliverables:**
- Consolidated 21 agents → 8 agents
- Pipeline graph 11 nodes → 8 nodes
- Version bump to v3.0.0
- Docker multi-stage build + docker-compose.yml
- GitHub Actions CI (tests + CodeQL + Dependabot)
- Comprehensive audit (150 items, 39 fixes, grade A-)
- OpenTelemetry + Azure Monitor telemetry
- 200+ tests passing (216/221)

### Week 14: Defense Prep (In Progress)

**Remaining:**
- Defense slides (20 slides)
- Demo video
- README polish
- Extra KB pairs if time permits

---

## 21. Test Suite

### Overview

- **Total tests**: 221
- **Passing**: 216 (97.7%)
- **Pre-existing failures**: 2 (async edge cases)
- **Skipped**: 3 (environment-dependent)

### Test Files by Layer

| Layer | Test File | Tests | Focus |
|-------|-----------|-------|-------|
| L2-A | `test_file_analysis.py` | 25 | FileProcessor, encoding, hashing, dedup |
| L2-A | `test_cross_file_deps.py` | — | Dependency resolution |
| L2-A | `test_data_lineage.py` | 5 | Data flow extraction |
| L2-A | `test_registry_writer.py` | — | SQLite idempotency |
| L2-B | `test_streaming.py` | 22 | Throughput < 2s, memory < 100MB, FSM |
| L2-C | `test_boundary_detector.py` | 20 | 79.3% accuracy on 721 blocks |
| L2-D | `test_complexity_agent.py` | 18 | 5 features, risk classification |
| L2-D | `test_strategy_agent.py` | 15 | Strategy routing, calibration |
| L2-C | `test_raptor.py` | 15 | Embeddings, clustering, tree |
| L2-E | `test_persistence.py` | 12 | SQLite dedup, Parquet threshold |
| L3 | `test_translation.py` | 25 | KB retrieval, failure modes, validation |
| L3 | `test_rag.py` | — | 3 RAG paradigms |
| L4 | `test_merge_retraining.py` | 18 | Script assembly, import dedup |
| Orch | `test_orchestration.py` | — | Checkpoint, audit, telemetry |
| Orch | `test_integration.py` | 30+ | End-to-end pipeline |
| Eval | `test_evaluation.py` | — | Ablation runner |
| Robust | `test_robustness_kb.py` | — | KB quality, drift monitoring |
| Regression | `test_boundary_accuracy.py` | — | CI guard: ≥ 79.3% |

### Running Tests

```bash
# Full suite
cd sas_converter
pytest tests/ -v

# Single layer
pytest tests/test_file_analysis.py -v
pytest tests/test_streaming.py -v
pytest tests/test_boundary_detector.py -v

# With coverage
pytest tests/ --cov=partition --cov-report=term-missing

# Week 1-2 tests only (L2-A)
pytest tests/test_file_analysis.py tests/test_cross_file_deps.py tests/test_data_lineage.py tests/test_registry_writer.py -v
```

---

## 22. Scripts & CLI Tools

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/run_pipeline.py` | **Primary CLI** — runs full 8-node pipeline | `python scripts/run_pipeline.py data/ --target python --redis redis://localhost:6379` |
| `main.py` | Legacy CLI (L2-A/B/C only) | `python main.py --file path.sas` |
| `examples/demo_pipeline.py` | Demo (no LLM needed) | `cd sas_converter && python examples/demo_pipeline.py` |
| `scripts/generate_kb_pairs.py` | Dual-LLM KB generation | `python scripts/generate_kb_pairs.py --count 50` |
| `scripts/expand_kb.py` | Expand KB to target | `python scripts/expand_kb.py --target 330` |
| `scripts/init_ablation_db.py` | Init ablation DB | `python scripts/init_ablation_db.py` |
| `scripts/analyze_ablation.py` | Analyze ablation results | `python scripts/analyze_ablation.py` |
| `scripts/kb_rollback.py` | Rollback KB example | `python scripts/kb_rollback.py --example-id <id> --to-version 1` |
| `scripts/submit_correction.py` | Submit human correction | `python scripts/submit_correction.py --partition-id <id>` |

---

## 23. Dependencies (requirements.txt)

### Core Framework
```
pydantic>=2.11
python-dotenv
sqlalchemy>=2.0
structlog>=25.0
```

### Parsing & Processing
```
chardet>=5.2
lark>=1.2
aiofiles>=24.1
pyarrow>=20.0
```

### LLM & Inference
```
openai>=1.82        # Azure OpenAI
groq>=0.25           # Groq Cloud
instructor>=1.8      # Structured output
tiktoken>=0.9        # Token counting
```

### ML & Embeddings
```
scikit-learn>=1.6
numpy>=2.2
sentence-transformers>=4.1
torch>=2.7
lancedb>=0.22
```

### Persistence & Graph
```
duckdb>=1.3
networkx>=3.5
redis>=5.2
```

### Orchestration & Telemetry
```
langgraph>=0.2
azure-monitor-opentelemetry>=1.6
opentelemetry-api>=1.25
```

### Testing & Utilities
```
pytest>=8.3
pytest-asyncio>=0.26
pytest-cov>=6.1
pyyaml>=6.0
jinja2>=3.1
markdown2>=2.5
```

---

## 24. Configuration Reference

### `config/project_config.yaml`

```yaml
logging:
  level: INFO              # DEBUG | INFO | WARNING | ERROR
  format: console          # console | json

llm:
  provider: azure          # azure | groq
  max_tokens: 6000
  azure:
    api_version: "2024-10-21"
    deployment_mini: "gpt-4o-mini"     # LOW risk blocks
    deployment_full: "gpt-4o"           # MOD/HIGH risk blocks

raptor:
  embedding_model: "nomic-ai/nomic-embed-text-v1.5"
  embedding_dim: 768
  max_cluster_depth: 3

complexity:
  ece_threshold: 0.12      # Retraining trigger
  success_threshold: 0.70  # Quality gate

graph:
  max_hop: 10              # DAG traversal depth cap
```

### Environment Variables (`.env`)

```
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...
GROQ_API_KEY=...
REDIS_URL=redis://localhost:6379/0
DUCKDB_PATH=analytics.duckdb
```

---

## 25. Known Limitations & Future Work

### Current Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|------------|
| Boundary accuracy 79.3% vs 90% target | Some blocks mis-detected | TOLERANCE=2, LLM fallback, corpus expansion |
| Single-machine design | No horizontal scaling | Future: distributed processing |
| CodeBLEU evaluation pending | Translation quality unquantified | Blocked on final KB expansion |
| Ablation study pending | RAPTOR advantage unconfirmed | Scheduled Week 12 |
| 2 pre-existing async test failures | Minor CI noise | Non-blocking, async edge cases |

### Future Work

1. **Distributed pipeline** — Multi-worker processing for large codebases
2. **PySpark target** — Currently Python-only, PySpark translation planned
3. **Interactive UI** — Web dashboard for conversion monitoring
4. **Larger gold corpus** — Expand from 50 to 200+ files for better accuracy
5. **Fine-tuned LLM** — Train specialized SAS→Python model on KB
6. **Language support** — Extend to R, SPSS, Stata conversion

---

## 26. Glossary

| Term | Definition |
|------|-----------|
| **BIC** | Bayesian Information Criterion — model selection metric for GMM clustering |
| **CodeBLEU** | Code-specific BLEU metric combining syntax, dataflow, and token overlap |
| **ECE** | Expected Calibration Error — measures confidence calibration quality |
| **FSM** | Finite State Machine — StreamAgent's parsing approach |
| **GMM** | Gaussian Mixture Model — soft clustering algorithm used by RAPTOR |
| **Gold Standard** | Manually annotated corpus of SAS files with verified block boundaries |
| **IVF** | Inverted File Index — LanceDB's approximate nearest neighbor index type |
| **KB** | Knowledge Base — verified SAS↔Python translation pairs in LanceDB |
| **LALR** | Look-Ahead Left-to-Right parser — Lark grammar type for SAS pre-validation |
| **LangGraph** | Framework for building stateful, multi-agent LLM applications |
| **PartitionIR** | Intermediate Representation — core data unit for one SAS code block |
| **PFE** | Projet de Fin d'Études — Final-year engineering project |
| **Platt Scaling** | Post-hoc calibration technique for classifier confidence scores |
| **RAPTOR** | Recursive Abstractive Processing for Tree-Organized Retrieval (ICLR 2024) |
| **SCC** | Strongly Connected Component — circular dependency group in DAG |
| **TOLERANCE** | ±2 line tolerance for boundary accuracy matching |
| **WAL** | Write-Ahead Logging — SQLite journal mode for crash safety |

---

> **Last updated**: March 2026 — Pipeline v3.0.0 — 8 agents, 8 nodes, 216/221 tests passing
