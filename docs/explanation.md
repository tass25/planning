# Codara — Complete Project Explanation (File by File)

> **Codara** is a SAS-to-Python conversion accelerator. It takes legacy SAS statistical programs, parses them, understands their structure, and translates them into equivalent Python code using AI — then formally verifies the result is correct. This document explains every mechanism, every file, every design decision.

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [Backend API Layer](#2-backend-api-layer)
3. [The 8-Node Pipeline (LangGraph)](#3-the-8-node-pipeline-langgraph)
4. [Node 1: File Processing (L2-A)](#4-node-1-file-processing-l2-a)
5. [Node 2: Streaming Parser (L2-B)](#5-node-2-streaming-parser-l2-b)
6. [Node 3: Chunking / Boundary Detection (L2-C)](#6-node-3-chunking--boundary-detection-l2-c)
7. [Node 4: RAPTOR Semantic Clustering (L2-C)](#7-node-4-raptor-semantic-clustering-l2-c)
8. [Node 5: Risk Routing / Complexity Scoring (L2-D)](#8-node-5-risk-routing--complexity-scoring-l2-d)
9. [Node 6: Persistence + Indexing (L2-E)](#9-node-6-persistence--indexing-l2-e)
10. [Node 7: Translation (L3) — The Core](#10-node-7-translation-l3--the-core)
11. [Node 8: Merge (L4)](#11-node-8-merge-l4)
12. [The Three RAG Paradigms](#12-the-three-rag-paradigms)
13. [LLM Provider Chain & Fallback Mechanism](#13-llm-provider-chain--fallback-mechanism)
14. [Verification Layer](#14-verification-layer)
15. [The Four Databases](#15-the-four-databases)
16. [Knowledge Base System](#16-knowledge-base-system)
17. [Resilience Mechanisms](#17-resilience-mechanisms)
18. [Authentication & Security](#18-authentication--security)
19. [Frontend](#19-frontend)
20. [CI/CD Pipeline](#20-cicd-pipeline)
21. [Docker & Azure Infrastructure](#21-docker--azure-infrastructure)
22. [Evaluation & Benchmarking](#22-evaluation--benchmarking)
23. [CDAIS — Formal Adversarial Testing (Deep Dive)](#23-cdais--formal-adversarial-testing-deep-dive)
24. [MIS — Migration Invariant Synthesis](#24-mis--migration-invariant-synthesis)
25. [HyperRAPTOR — Poincaré Ball Clustering](#25-hyperraptor--poincaré-ball-clustering)
26. [QLoRA Fine-Tuning Pipeline](#26-qlora-fine-tuning-pipeline)
27. [The 6 Failure Modes (Detailed)](#27-the-6-failure-modes-detailed)
28. [KB Dual-LLM Generation Chain](#28-kb-dual-llm-generation-chain)
29. [Week-by-Week Build History](#29-week-by-week-build-history)
30. [File-by-File Reference](#30-file-by-file-reference)

---

## 1. High-Level Architecture

Codara is a **three-tier stack**:

```
User (Browser)
    │
    ▼
Frontend (React 18 + Vite, port 5173)
    │  /api proxy
    ▼
Backend API (FastAPI, port 8000)
    │  BackgroundTasks
    ▼
Pipeline Engine (LangGraph StateGraph, 8 nodes, 20+ sub-agents)
    │
    ├──► 3 LLM Providers (Ollama → Azure OpenAI → Groq)
    ├──► 4 Databases (SQLite, Redis, LanceDB, DuckDB)
    └──► Verification (Z3, CDAIS, Sandbox, Cross-Verify)
```

**How it works end-to-end:**
1. A user uploads a `.sas` file through the web interface.
2. The backend saves it to disk and creates a database record.
3. A background task launches the 8-node LangGraph pipeline.
4. The pipeline parses the SAS code, breaks it into logical blocks, scores their complexity, translates each block to Python using AI with knowledge base examples, verifies the translation formally, and merges everything into a final Python script.
5. The frontend polls every 1.2 seconds to show real-time progress.
6. The user downloads the result: Python code + a detailed conversion report.

---

## 2. Backend API Layer

### `backend/api/main.py` — Application Entry Point
The FastAPI application is defined here. It:
- Configures CORS (allowing localhost:5173, :8080, :8000 and any configured frontend URL).
- Includes all route modules (auth, conversions, knowledge_base, admin, analytics, notifications, settings).
- Registers middleware (structured logging, error handling).
- Seeds the database on first boot: creates admin and user accounts with random passwords (or from env vars `CODARA_ADMIN_PASSWORD` / `CODARA_USER_PASSWORD`), printed to stdout.
- Exposes a `/api/health` endpoint returning `{"status": "ok", "version": "3.0.0"}`.

### `backend/api/core/database.py` — SQLAlchemy Models
Defines **8 SQLite tables** using SQLAlchemy ORM:
- **`UserRow`**: id, email, name, hashed_password, role (admin/user/viewer), status, conversion_count, email_verified, github_id, verification_token.
- **`ConversionRow`**: id, user_id, file_name, status (queued/running/completed/partial/failed), runtime, duration, accuracy, sas_code, python_code, validation_report, merge_report.
- **`ConversionStageRow`**: id, conversion_id, stage, status, latency, retry_count, warnings (JSON), description, timestamps. Tracks the 8 display stages for the frontend progress bar.
- **`KBEntryRow`**: Knowledge base entries (SAS snippet + Python translation + category + confidence).
- **`KBChangelogRow`**: Version history for KB entries (add/edit/rollback/delete).
- **`AuditLogRow`**: LLM call audit logs (model, latency, cost, prompt_hash, success).
- **`CorrectionRow`**: Human corrections submitted by users after conversion.
- **`NotificationRow`**: User notifications (info/success/warning/error).

The database runs in **WAL mode** (Write-Ahead Logging) with foreign keys enforced, giving ACID guarantees without a heavy server like PostgreSQL.

### `backend/api/core/auth.py` — Authentication
- **JWT tokens** (HS256 algorithm, 24-hour expiry) signed with `CODARA_JWT_SECRET` env var.
- **bcrypt** password hashing via passlib.
- `create_access_token()` encodes user ID, email, and role into the JWT payload.
- `get_current_user()` dependency validates the `Authorization: Bearer <token>` header on every protected endpoint.

### `backend/api/core/schemas.py` — Pydantic Schemas
All request/response models for the API: `LoginRequest`, `SignupRequest`, `AuthResponse`, `UserOut`, `ConversionOut`, `SasFileOut`, `PartitionOut`, `KBEntryOut`, `AnalyticsData`, etc. These validate all API input/output using Pydantic v2.

### `backend/api/core/deps.py` — Dependencies
Shared FastAPI dependencies like database session injection.

### `backend/api/core/repositories/` — Repository Pattern
- **`conversion_repository.py`**: CRUD operations for conversions (create, update status, get by ID, list by user).
- **`kb_repository.py`**: CRUD for knowledge base entries.
- **`user_repository.py`**: CRUD for user accounts.

These abstract the database access away from the route handlers.

### `backend/api/middleware/error_handler.py` — Error Handling
Global exception handler that catches unhandled errors and returns structured JSON responses with appropriate HTTP status codes. Prevents stack traces from leaking to the client.

### `backend/api/middleware/logging_middleware.py` — Request Logging
Logs every HTTP request with structlog: method, path, status code, latency. Useful for debugging and monitoring.

### `backend/api/routes/auth.py` — Authentication Routes
- **`POST /api/auth/login`**: Validates email + password against bcrypt hash in the database. Returns JWT token + user info.
- **`POST /api/auth/signup`**: Creates a new user with email verification token. Sends welcome notifications.
- **`POST /api/auth/verify-email`**: Validates the verification token and marks the account as verified.
- **`GET /api/auth/github/url`**: Returns the GitHub OAuth authorization URL (using `GITHUB_CLIENT_ID`).
- **`POST /api/auth/github/callback`**: Full GitHub OAuth flow — exchanges the authorization code for an access token, fetches the user's GitHub profile and primary email, creates or links the account, and returns a JWT. If a user with the same email already exists, it links the GitHub ID to that existing account.
- **`GET /api/auth/me`**: Returns the current user's profile (requires valid JWT).
- **`POST /api/auth/logout`**: Returns success (JWT is stateless, client discards the token).
- **Rate limiting**: In-memory sliding window — max 5 attempts per minute per IP per endpoint. Prevents brute-force attacks.

### `backend/api/routes/conversions.py` — Conversion Routes
This is where the pipeline gets triggered:
- **`POST /api/conversions/upload`**: Receives `.sas` files via multipart form upload. Each file gets a unique ID (`file-{uuid_hex8}`) and is saved to `backend/uploads/{file_id}/`. Returns file metadata.
- **`POST /api/conversions/start`**: Creates a ConversionRow (status=queued), then launches the **real pipeline** via FastAPI's `BackgroundTasks`. The background task calls `pipeline_service.run_pipeline()` which instantiates the `PartitionOrchestrator` and runs the full 8-node LangGraph pipeline. While it runs, it updates the ConversionStageRow records so the frontend can show progress.
- **`GET /api/conversions/{id}`**: Returns the conversion record with all stage statuses. The frontend polls this every 1.2 seconds.
- **`GET /api/conversions/{id}/download`**: Creates a zip file containing the translated Python code and the HTML conversion report.
- **`GET /api/conversions/{id}/stream`**: Server-Sent Events (SSE) endpoint for real-time streaming of conversion progress.
- **`POST /api/conversions/{id}/corrections`**: Accepts human corrections (corrected code + explanation). The correction is saved and automatically ingested into the Knowledge Base for future translations.

**Stage mapping**: The API maps the real 8 pipeline node names (`file_process, streaming, chunking, raptor, risk_routing, persist_index, translation, merge`) to 8 display names (`file_process, sas_partition, strategy_select, translate, validate, repair, merge, finalize`) that the frontend shows.

### `backend/api/routes/knowledge_base.py` — KB Management
CRUD endpoints for the knowledge base: list entries, create new SAS→Python pairs, update, delete, view changelog history, and search using semantic similarity.

### `backend/api/routes/admin.py` — Admin Routes
Admin-only endpoints (requires `role=admin` in the JWT):
- List/update/delete users.
- View audit logs (all LLM calls with latency and cost data).
- System health (database sizes, Redis status, LLM provider availability).
- Pipeline configuration (read/update runtime settings).
- File registry (all processed files and their metadata).

### `backend/api/routes/analytics.py` — Analytics
Returns conversion statistics: total conversions, success rate, average duration, time-series data for charting.

### `backend/api/routes/notifications.py` — Notifications
User notification CRUD: list unread notifications, mark as read.

### `backend/api/routes/settings.py` — User Settings
Update user preferences (default runtime, email notification toggle).

### `backend/api/services/pipeline_service.py` — Pipeline Service
The bridge between the API layer and the pipeline engine. `run_pipeline()`:
1. Updates the conversion status to "running".
2. Creates ConversionStageRow records for all 8 stages.
3. Instantiates `PartitionOrchestrator` with the Redis URL and DuckDB path.
4. Calls `orchestrator.run(input_paths)`.
5. As the pipeline progresses, updates each stage's status, latency, and description.
6. When complete, writes the final Python code and report back to the ConversionRow.
7. On failure, marks the conversion as "failed" with the error message.

### `backend/api/services/translation_service.py` — Quick Translation
A separate, simpler LLM translation function for the "quick convert" feature. It uses a single LLM call (not the full pipeline) for fast single-file translations. Has its own `PromptManager` instance.

### `backend/api/services/blob_service.py` — File Storage
Handles file upload/download operations. Saves uploaded SAS files to `backend/uploads/` with unique directory names.

### `backend/api/services/conversion_service.py` — Conversion Business Logic
Higher-level conversion operations: creating conversion records, updating status, computing accuracy metrics.

### `backend/api/services/queue_service.py` — Queue Management
Manages the conversion queue: enqueue, dequeue, prioritization.

---

## 3. The 8-Node Pipeline (LangGraph)

### `backend/partition/orchestration/orchestrator.py` — The Orchestrator
This is the heart of the system. The `PartitionOrchestrator` builds a **LangGraph StateGraph** — a directed acyclic graph where each node is a Python async function that receives the full pipeline state and returns a partial update.

**Why LangGraph (not LangChain)?**
LangGraph gives **explicit state machines** with typed state. Each node reads/writes to a shared `PipelineState` TypedDict. This means:
- Deterministic execution order (no magic chain routing).
- Per-node checkpointing — if the pipeline crashes at node 5, Redis has the state from node 4.
- Error isolation — a node failure appends to `state["errors"]` instead of crashing everything.

**The 8 nodes in order:**
```
file_process → streaming → chunking → raptor → risk_routing → persist_index → translation → merge → END
```

**Error handling philosophy:**
- **Node 1 (file_process) failure is FATAL** — without file metadata, nothing downstream can work. The pipeline raises immediately.
- **All other node failures are NON-FATAL** — the node logs the error, appends to `state["errors"]`, and the pipeline continues. This means you always get *some* output, even if partial.

**Agent caching:** The `_get_agent(key, factory)` pattern ensures each agent (which may load ML models, open DB connections, or spin up LLM clients) is only instantiated once per pipeline run.

### `backend/partition/orchestration/state.py` — Pipeline State
Defines `PipelineState` as a TypedDict (not Pydantic — LangGraph requires TypedDict). Contains all fields passed between nodes:
- `input_paths`, `target_runtime`, `stage` (current pipeline stage enum)
- `file_metas`, `file_ids`, `cross_file_deps` (from node 1)
- `chunks_by_file` (from node 2)
- `partitions`, `partition_count` (from node 3)
- `raptor_nodes` (from node 4)
- `complexity_computed`, `scc_groups` (from node 5)
- `persisted_count` (from node 6)
- `conversion_results`, `validation_passed` (from node 7)
- `merge_results` (from node 8)
- `errors`, `warnings`, `trace_id`, `run_id`, `pipeline_version`

### `backend/partition/orchestration/audit.py` — DuckDB Audit Logger
Every LLM call in the pipeline is logged to DuckDB with:
- Agent name, model name, prompt hash, response hash
- Latency in milliseconds, success/failure, error message
- Used for analytics, debugging, and cost tracking

Works as a context manager: `with audit.log_call("agent_name", "model", prompt) as call: ...`

### `backend/partition/orchestration/checkpoint.py` — Redis Checkpointing
**Why Redis?** Redis provides **atomic writes** for crash recovery. If the pipeline crashes mid-execution, the checkpoint in Redis preserves the state so it can resume from the last saved point instead of starting over.

**How it works:**
- Every 50 processed blocks, the pipeline serializes the current partition data to JSON and stores it in Redis with a key like `partition:{file_id}:checkpoint:{block_num}`.
- TTL is 24 hours (old checkpoints auto-expire).
- On startup, the orchestrator checks for existing checkpoints and resumes from the latest one.
- **Degraded mode**: If Redis is unavailable, the pipeline continues without checkpointing. A warning is logged, but no data is lost — you just lose crash recovery capability.

### `backend/partition/orchestration/telemetry.py` — Azure Monitor Telemetry
Sends traces, metrics, and events to Azure Application Insights via OpenTelemetry. If `APPLICATIONINSIGHTS_CONNECTION_STRING` is not set, all telemetry calls are no-ops (the pipeline works fine without it).

### `backend/partition/orchestration/events.py` — Pipeline Events
Event system for notifying listeners about pipeline stage transitions.

### `backend/partition/orchestration/execution_state.py` — Execution State Tracker
Tracks which SAS datasets have been produced/consumed during pipeline execution.

### `backend/partition/base_agent.py` — Base Agent ABC
Every agent in the pipeline inherits from `BaseAgent`:
- Has a `trace_id` (UUID) for distributed tracing.
- Has a bound structlog logger tagged with the agent name.
- Must implement `async def process(...)`.
- Provides the `@with_retry` decorator for automatic retries with exponential backoff.

### `backend/partition/models/partition_ir.py` — PartitionIR
The **core unit of work** in the pipeline. Each SAS code block becomes a `PartitionIR` (Intermediate Representation):
- `block_id` (UUID): unique identifier
- `file_id` (UUID): which file it came from
- `partition_type` (enum): DATA_STEP, PROC_BLOCK, SQL_BLOCK, MACRO_DEFINITION, etc.
- `source_code`: the raw SAS code
- `line_start`, `line_end`: line numbers in the original file
- `risk_level`: LOW, MODERATE, HIGH, or UNCERTAIN
- `conversion_status`: PENDING, SUCCESS, PARTIAL, FAILED
- `dependencies`: list of other block UUIDs this block depends on
- `metadata`: dict for arbitrary extra data (complexity score, SCC ID, RAPTOR node IDs, etc.)

### `backend/partition/models/enums.py` — Enumerations
- **`PartitionType`** (10 values): DATA_STEP, PROC_BLOCK, SQL_BLOCK, MACRO_DEFINITION, MACRO_INVOCATION, CONDITIONAL_BLOCK, LOOP_BLOCK, GLOBAL_STATEMENT, INCLUDE_REFERENCE, COMMENT_BLOCK
- **`RiskLevel`**: LOW, MODERATE, HIGH, UNCERTAIN
- **`ConversionStatus`**: PENDING, SUCCESS, PARTIAL, FAILED
- **`PartitionStrategy`**: DIRECT, RAG_ASSISTED, TEMPLATE_BASED, MANUAL_REVIEW

### `backend/partition/models/conversion_result.py` — ConversionResult
The output of translating one partition: `conversion_id`, `block_id`, `file_id`, `python_code`, `imports`, `status`, `llm_confidence`, `failure_mode_flagged`, `model_used`, `kb_examples_used`, `retry_count`, `trace_id`.

### `backend/partition/models/file_metadata.py` — FileMetadata
Metadata about a source SAS file: `file_id`, `file_path`, `file_name`, `file_size`, `line_count`, `encoding`, `has_macros`, `has_includes`, `has_sql`.

---

## 4. Node 1: File Processing (L2-A)

**Purpose**: Scan input files, analyze their structure, register them in the system, and resolve cross-file dependencies.

### `backend/partition/entry/file_processor.py` — FileProcessor (Facade)
Orchestrates three sub-agents in sequence:
1. **FileAnalysisAgent** → scans each file
2. **CrossFileDepsResolver** → finds inter-file dependencies
3. **RegistryWriterAgent** → persists metadata to SQLite

### `backend/partition/entry/file_analysis_agent.py` — FileAnalysisAgent
Reads each SAS file and extracts:
- Line count, file size, encoding detection
- Whether the file uses macros (`%MACRO`), includes (`%INCLUDE`), or SQL (`PROC SQL`)
- Dataset references (DATA step outputs and inputs)
- Library references (LIBNAME statements)

### `backend/partition/entry/cross_file_dep_resolver.py` — CrossFileDepsResolver
When multiple SAS files are uploaded together, they often depend on each other (file A creates a dataset that file B reads). This agent:
- Builds a dependency graph: which files produce which datasets, which files consume them.
- Detects circular dependencies between files.
- Returns a dict mapping `file_id → list[dependent_file_ids]`.

### `backend/partition/entry/data_lineage_extractor.py` — DataLineageExtractor
Tracks data lineage: for each dataset referenced in the SAS code, traces where it was created, transformed, and consumed. This information feeds into the GraphRAG paradigm later.

### `backend/partition/entry/registry_writer_agent.py` — RegistryWriterAgent
Persists all file metadata to the SQLite database for tracking and retrieval.

---

## 5. Node 2: Streaming Parser (L2-B)

**Purpose**: Read SAS files line-by-line and produce a stream of annotated code chunks, tracking the FSM (finite state machine) state at each point.

### `backend/partition/streaming/pipeline.py` — `run_streaming_pipeline()`
Wires `StreamAgent` and `StateAgent` together via an `asyncio.Queue`:
- `StreamAgent` (producer) reads the file and emits `LineChunk` objects into the queue.
- `StateAgent` (consumer) processes each chunk and updates the FSM state.
- Backpressure: the queue has a bounded size, so if the consumer is slow, the producer blocks instead of flooding memory.

### `backend/partition/streaming/stream_agent.py` — StreamAgent (Producer)
Reads the SAS file line-by-line and wraps each line (or group of lines) into a `LineChunk` object with:
- The raw text
- Line number
- Whether it's inside a comment or string literal

### `backend/partition/streaming/state_agent.py` — StateAgent (Consumer / FSM)
A **pure-Python finite state machine** for SAS parsing. No LLM, no I/O, no network — just regex and string checks. It maintains a `ParsingState` that tracks:
- **Current block type**: DATA_STEP, PROC_BLOCK, SQL_BLOCK, MACRO_DEFINITION, etc.
- **Block nesting depth**: `%DO` / `%IF` inside macros can nest arbitrarily deep.
- **Macro call stack**: push on `%MACRO`, pop on `%MEND`.
- **Variable scope**: recently assigned variable names.
- **Active dependencies**: `%INCLUDE` / `LIBNAME` references.
- **Comment and string tracking**: prevents misinterpreting code inside comments or strings.

**Key SAS parsing rules implemented:**
- `DATA <name>` opens a DATA_STEP, closed by `RUN;`
- `PROC <name>` opens a PROC_BLOCK, closed by `RUN;` or `QUIT;`
- `PROC SQL` opens a SQL_BLOCK, closed by `QUIT;`
- `%MACRO <name>` opens a MACRO_DEFINITION, closed by `%MEND;`
- **Implicit closure**: when a new `DATA` or `PROC` starts, any open DATA_STEP or PROC_BLOCK is implicitly closed (SAS allows this).
- `%LET`, `OPTIONS`, `LIBNAME`, `FILENAME` are GLOBAL_STATEMENTs.

### `backend/partition/streaming/models.py` — Data Models
Defines `LineChunk` (a parsed line with metadata) and `ParsingState` (the FSM snapshot).

### `backend/partition/streaming/streaming_parser.py` — Alternative Parser
A simpler streaming parser variant used in some code paths.

---

## 6. Node 3: Chunking / Boundary Detection (L2-C)

**Purpose**: Take the annotated stream of code chunks and identify where each logical block starts and ends — i.e., find the boundaries between SAS code blocks.

### `backend/partition/chunking/chunking_agent.py` — ChunkingAgent (Facade)
Orchestrates:
1. **BoundaryDetectorAgent**: finds block boundaries
2. **PartitionBuilder**: creates `PartitionIR` objects from the detected boundaries

### `backend/partition/chunking/boundary_detector.py` — BoundaryDetector
This is a **hybrid deterministic + LLM system**:

**Step 1 — Deterministic detection (~80% of cases):**
Uses a Lark grammar parser and regex patterns to identify SAS block boundaries. Rules:
- `DATA <name>;` ... `RUN;` → DATA_STEP boundary
- `PROC <name>;` ... `RUN;`/`QUIT;` → PROC_BLOCK boundary
- `PROC SQL;` ... `QUIT;` → SQL_BLOCK boundary
- `%MACRO <name>;` ... `%MEND;` → MACRO_DEFINITION boundary
- `%INCLUDE` → INCLUDE_REFERENCE boundary
- And many more patterns

**Step 2 — LLM fallback (~20% of cases):**
When the deterministic parser can't figure out a boundary (ambiguous SAS code, complex macro nesting), it falls back to the `LLMBoundaryResolver`.

### `backend/partition/chunking/llm_boundary_resolver.py` — LLMBoundaryResolver
Sends the ambiguous code to an LLM (Azure GPT-4o-mini) with a structured prompt asking it to identify the block type and boundaries. Uses `instructor` for structured output (the LLM must return a specific Pydantic model).

### `backend/partition/chunking/partition_builder.py` — PartitionBuilder
Takes the boundary detection results and constructs `PartitionIR` objects, assigning each block:
- A unique `block_id` (UUID)
- The source code text
- Line start/end numbers
- The detected `PartitionType`
- Initial `risk_level` (set to UNCERTAIN — refined later by the ComplexityAgent)

### `backend/partition/chunking/models.py` — Chunking Models
Data classes for boundary detection results.

---

## 7. Node 4: RAPTOR Semantic Clustering (L2-C)

**Purpose**: Group semantically related partitions into clusters, then build a hierarchical tree of summaries. This tree powers the RAG retrieval — when translating a partition, RAPTOR helps find the most relevant context.

**What is RAPTOR?** (Recursive Abstractive Processing for Tree-Organized Retrieval)
Instead of just doing flat keyword search, RAPTOR:
1. Embeds each partition into a 768-dimensional vector.
2. Clusters similar partitions using Gaussian Mixture Models (GMM).
3. Summarizes each cluster into a single text.
4. Recursively clusters the summaries until you have a tree with a single root.
5. The tree enables hierarchical retrieval: broad context from upper levels, specific details from leaves.

### `backend/partition/raptor/raptor_agent.py` — RAPTORPartitionAgent (Facade)
Orchestrates: `NomicEmbedder → GMMClusterer → ClusterSummarizer → RAPTORTreeBuilder`

### `backend/partition/raptor/embedder.py` — NomicEmbedder
Uses the `nomic-embed-text-v1.5` sentence transformer model (768 dimensions) to embed SAS code into dense vectors. The model runs on CPU via PyTorch.
- **Singleton pattern**: `get_embedder()` returns a cached instance so the model is loaded only once.
- The model is ~270MB and takes a few seconds to load on first call.

### `backend/partition/raptor/clustering.py` — GMMClusterer
Uses scikit-learn's `GaussianMixture` to cluster partition embeddings:
- **Threshold τ = 0.72**: a partition is assigned to a cluster only if its posterior probability exceeds this threshold. This prevents forcing dissimilar partitions into the same cluster.
- **Automatic component selection**: tries 2 to min(10, n_samples) components, picks the best by BIC (Bayesian Information Criterion).
- **Edge case**: if fewer than 2 partitions exist, clustering is skipped entirely (can't cluster 1 item).

### `backend/partition/raptor/summarizer.py` — ClusterSummarizer
Takes a cluster of SAS code partitions and generates a natural language summary using an LLM. The summary captures the high-level intent of the cluster (e.g., "This cluster handles customer data ETL: loading raw transactions, filtering by date, and computing aggregates").

### `backend/partition/raptor/tree_builder.py` — RAPTORTreeBuilder
Builds the hierarchical tree:
- **Level 0 (leaves)**: each partition is a leaf node.
- **Level 1**: clusters of leaves, each with a summary.
- **Level 2+**: clusters of clusters (recursive), until one root.
- Each node stores its embedding, text, and back-links to its children.

### `backend/partition/raptor/lancedb_writer.py` — LanceDB RAPTOR Writer
Writes RAPTOR tree nodes to LanceDB for persistent retrieval.

---

## 8. Node 5: Risk Routing / Complexity Scoring (L2-D)

**Purpose**: Score each partition's complexity and assign a translation strategy.

### `backend/partition/complexity/risk_router.py` — RiskRouter (Facade)
Orchestrates: `ComplexityAgent → StrategyAgent`

### `backend/partition/complexity/complexity_agent.py` — ComplexityAgent
Scores each partition's risk level (LOW / MODERATE / HIGH) using a **hybrid ML + rule-based approach**:

**ML model (when available):**
- A scikit-learn classifier (`complexity_model.joblib`) trained on labeled SAS code blocks.
- Features: 14 numerical features extracted from the code.
- If the model file exists and matches the feature schema, its predictions are used.

**Rule-based fallback (always available):**
~20 prioritized rules based on SAS-specific patterns:
- **HIGH triggers**: `CALL EXECUTE` (score 0.92), SQL subquery (0.88), `MERGE + RETAIN` (0.87), `CALL SYMPUT` (0.85), nesting depth >= 3 (0.84), lines >= 80 (0.78)
- **MODERATE triggers**: `RETAIN` (0.80), `MERGE` (0.78), `ARRAY` (0.76), nesting >= 2 (0.75)
- **LOW**: small code + simple type + no SAS-specific patterns

### `backend/partition/complexity/features.py` — Feature Extraction
Extracts 14 features from SAS source code:
- 6 structural features: line count, token count, nesting depth, distinct datasets, dependency count, type weight
- 8 SAS-specific pattern indicators: RETAIN, FIRST./LAST., MERGE, hash objects, SQL subqueries, CALL SYMPUT, PROC TRANSPOSE/REPORT, ARRAY, DO loops

### `backend/partition/complexity/strategy_agent.py` — StrategyAgent
Maps risk level to translation strategy:
- **LOW** → `DIRECT` (simple one-shot translation)
- **MODERATE** → `RAG_ASSISTED` (retrieve examples from KB)
- **HIGH** → `RAG_ASSISTED` with extra context and retries
- **UNCERTAIN** → `MANUAL_REVIEW` (flagged for human review)

---

## 9. Node 6: Persistence + Indexing (L2-E)

**Purpose**: Save partition data to SQLite and build a dependency graph.

### `backend/partition/persistence/persistence_agent.py` — PersistenceAgent
Writes all `PartitionIR` objects to the SQLite database for durability. This ensures that if the pipeline crashes after this node, the partitions are recoverable.

### `backend/partition/index/index_agent.py` — IndexAgent
Builds the partition index using NetworkX for efficient dependency lookups during translation.

### `backend/partition/index/graph_builder.py` — NetworkXGraphBuilder
Builds a **directed graph** where:
- Each node is a `PartitionIR` (identified by `block_id`).
- Edges represent dependencies (block A depends on block B).
- **SCC detection** (Strongly Connected Components): identifies circular dependencies using Tarjan's algorithm. Circular dependencies are batched for translation — all members of an SCC are translated together.

---

## 10. Node 7: Translation (L3) — The Core

This is the most complex and important node. It translates every SAS partition into Python code.

### `backend/partition/translation/translation_pipeline.py` — TranslationPipeline
The end-to-end L3 pipeline for each partition:

```
For each partition:
  1. TRANSLATE: TranslationAgent produces Python code via LLM
  2. VALIDATE: ValidationAgent checks syntax (ast.parse) + runs in sandbox (exec)
  3. If validation fails:
     a. Classify the error (syntax vs semantic)
     b. Analyse the error (generate repair hints)
     c. Retry with error context injected into the prompt
     d. Repeat up to MAX_RETRIES times
  4. VERIFY: Z3VerificationAgent attempts formal proofs
  5. CDAIS: Adversarial testing with synthesized edge cases
  6. If verification finds a counterexample → re-queue at HIGH risk for one more retry
  7. Log result to DuckDB
```

**Retry budget differentiation:**
- Base: 2 retries
- MACRO/SQL blocks: +1 extra retry (these are harder to translate)
- Semantic errors (syntax passes but exec fails): +1 extra retry

**Stagnation detection:**
If two consecutive retries produce identical code, the pipeline stops retrying (the LLM is stuck and wasting API calls).

### `backend/partition/translation/translation_agent.py` — TranslationAgent
The actual LLM translation logic. For each partition:

1. **Deterministic shortcut** (`deterministic_translator.py`): checks if the SAS code matches a well-known pattern that can be translated without an LLM (e.g., simple PROC PRINT, PROC SORT). If yes, returns immediately — no LLM cost.

2. **Failure mode detection** (`failure_mode_detector.py`): scans the SAS code for 6 known problematic patterns:
   - RETAIN with FIRST./LAST. (group processing)
   - Correlated subqueries in PROC SQL
   - MERGE with IN= dataset options
   - CALL EXECUTE / CALL SYMPUT (dynamic code generation)
   - HASH objects (SAS-specific data structure)
   - Complex ARRAY operations

3. **Business logic enrichment**: macro expansion, SAS format hints, SAS built-in function hints, type inference.

4. **RAG Router** → selects Static/GraphRAG/Agentic paradigm and builds the translation prompt with KB examples (see [Section 12](#12-the-three-rag-paradigms)).

5. **LLM translation** (full fallback chain):
   - Try **Ollama** (minimax-m2.7:cloud / nemotron-3-super:cloud) → free, primary
   - If Ollama fails → try **Azure OpenAI** (GPT-4o for MOD/HIGH, GPT-4o-mini for LOW)
   - If Azure fails → try **Groq** (LLaMA-3.3-70B) → free tier, last resort
   - If all fail → mark as PARTIAL status

6. **Cross-verification (Prompt C)**: after getting a translation, sends it to a *different* LLM provider for independent verification. The verifier checks if the Python code is semantically equivalent to the SAS original. If `confidence < 0.75`, triggers a retry.

7. **Reflexion retry**: if cross-verification or validation fails, the agent reflects on what went wrong and generates a self-critique, which is injected into the next translation prompt.

### `backend/partition/translation/validation_agent.py` — ValidationAgent
Post-translation validation in 2 steps:

**Step 1 — Syntax check** (`ast.parse()`):
Parses the Python code into an AST. If this fails, the code has syntax errors.

**Step 2 — Execution sandbox** (`exec()` in isolated subprocess):
Actually runs the translated Python code to check for runtime errors.

**Sandbox security** (critical):
- Uses `multiprocessing.Process` (not threads) for true isolation.
- Communication via `multiprocessing.Queue` (not Manager — Manager spawns a separate process that eats the timeout budget on Windows).
- **Removed builtins**: `open`, `__import__`, `exec`, `eval`, `compile`, `exit`, `quit`, `input`, `breakpoint` — the sandboxed code cannot access the filesystem or import arbitrary modules.
- **Hard timeout**: 15 seconds on Windows, 8 seconds on Linux. If the code doesn't finish, the process is killed via `.kill()` (not `.join(timeout)` which leaks threads).
- **Auto-namespace** (`_AutoNamespace`): a magic dict that automatically provides a synthetic 100-row DataFrame for any undefined variable. This lets translated code reference SAS dataset names (`transactions`, `customers`, etc.) without NameError, even without real input files. The DataFrame has 25+ columns with common SAS patterns (id, amount, date, category, etc.).

### `backend/partition/translation/deterministic_translator.py` — Deterministic Translator
Pattern-matched translations that don't need an LLM:
- Simple PROC PRINT → `print(df)`
- Simple PROC SORT → `df.sort_values(...)`
- Simple %LET → variable assignment
- Returns `None` if no deterministic pattern matches → falls through to LLM.

### `backend/partition/translation/failure_mode_detector.py` — Failure Mode Detector
6 regex-based rules that detect known problematic SAS patterns. When a failure mode is detected, the information is injected into the LLM prompt so it knows to pay extra attention to that pattern.

### `backend/partition/translation/kb_query.py` — KBQueryClient
Queries the LanceDB knowledge base for similar SAS→Python examples:
- Embeds the query SAS code using NomicEmbedder.
- Performs cosine similarity search in LanceDB.
- Returns the top-k most similar examples with their Python translations.
- Results are injected into the translation prompt as few-shot examples.

### `backend/partition/translation/macro_expander.py` — Macro Expander
Expands SAS macro variables (`&var`, `%LET var = value`) before translation, so the LLM sees the resolved values.

### `backend/partition/translation/format_mapper.py` — Format Mapper
Maps SAS display formats (like `DOLLAR12.2`, `MMDDYY10.`) to their Python equivalents. Returns hint blocks injected into the prompt.

### `backend/partition/translation/sas_builtins.py` — SAS Built-in Functions
Maps SAS built-in functions (like `INTCK`, `INTNX`, `CATX`, `COALESCEC`) to their Python equivalents. Returns hint blocks injected into the prompt.

### `backend/partition/translation/sas_type_inferencer.py` — SAS Type Inferencer
Infers variable types from SAS code (numeric vs character, date/time formats) so the LLM can produce correctly typed Python code.

### `backend/partition/translation/error_classifier.py` — Error Classifier
Classifies validation errors as SYNTAX (ast.parse failure) or SEMANTIC (exec failure). This determines the retry strategy — syntax errors need a different repair approach than semantic errors.

### `backend/partition/translation/error_analyst.py` — Error Analyst
Analyses validation errors and generates specific repair hints for the LLM. For example: "NameError: 'INTCK' is not defined → Use dateutil.relativedelta instead of SAS INTCK function."

### `backend/partition/translation/semantic_validator.py` — Semantic Validator
Additional semantic checks beyond syntax and execution:
- Checks that all SAS datasets referenced in input are consumed in the Python code.
- Checks that output datasets are produced.
- Checks for common translation mistakes (e.g., using `iterrows()` instead of vectorized operations).

### `backend/partition/translation/lineage_guard.py` — Lineage Guard
Validates data lineage: ensures the translated code reads from and writes to the same logical datasets as the original SAS code.

### `backend/partition/translation/dummy_data_generator.py` — Dummy Data Generator
Generates synthetic DataFrames for testing translations in the sandbox.

---

## 11. Node 8: Merge (L4)

**Purpose**: Take all translated partitions and merge them into a cohesive final Python script, consolidating imports, injecting dependencies, and generating a report.

### `backend/partition/merge/merge_agent.py` — MergeAgent (Facade)
Orchestrates: `ScriptMerger (ImportConsolidator + DependencyInjector) → ReportAgent`

### `backend/partition/merge/script_merger.py` — ScriptMerger
Merges all translated Python partitions into a single script, respecting dependency order. Uses the NetworkX graph to determine the correct ordering (topological sort).

### `backend/partition/merge/import_consolidator.py` — ImportConsolidator
Collects all `import` statements from all partitions and deduplicates them. Places them at the top of the merged script. Handles:
- `import pandas as pd` (only include once even if 10 partitions need it)
- `from datetime import datetime, timedelta` (merge partial imports)
- Standard library vs third-party ordering

### `backend/partition/merge/dependency_injector.py` — DependencyInjector
If partition B depends on partition A (B reads a dataset that A creates), the injector ensures A's code appears before B's in the merged script.

### `backend/partition/merge/namespace_checker.py` — Namespace Checker
Verifies that all variables and DataFrames referenced in the merged script are properly defined before use.

### `backend/partition/merge/report_agent.py` — ReportAgent
Generates a detailed HTML conversion report:
- Summary statistics (partitions translated, accuracy, models used)
- Per-partition details (SAS source, Python output, confidence score, failure modes, verification results)
- Warnings and errors encountered

---

## 12. The Three RAG Paradigms

RAG (Retrieval-Augmented Generation) provides the LLM with relevant examples from the knowledge base before translation. Codara uses **three different RAG paradigms** depending on the partition's complexity.

### `backend/partition/rag/router.py` — RAGRouter
Selects the paradigm based on:
- **Static RAG**: LOW risk, no dependencies, no SCC membership
- **GraphRAG**: partition has cross-file dependencies or SCC membership
- **Agentic RAG**: MODERATE/HIGH/UNCERTAIN risk, failure mode detected, or retry

### `backend/partition/rag/static_rag.py` — Static RAG
The simplest paradigm. Steps:
1. Embed the SAS source code using NomicEmbedder.
2. Query LanceDB for the top-k most similar SAS→Python examples.
3. Build a prompt with the examples as few-shot context.
4. Use the `translation_static.j2` Jinja2 template.

**When to use**: simple, self-contained blocks like `PROC PRINT`, `PROC SORT`, basic DATA steps.

### `backend/partition/rag/graph_rag.py` — GraphRAG
For partitions with inter-dependencies. Steps:
1. Start with Static RAG's top-k examples.
2. Traverse the dependency graph: find all partitions this block depends on or that depend on it (up to `hop_cap=3` hops).
3. Include the translated code of dependencies as context (so the LLM knows what variables/datasets are available).
4. If the partition is in an SCC (circular dependency), include all SCC members' code.
5. Use the `translation_graph.j2` template.

**When to use**: a DATA step that reads a dataset created by another DATA step; a MERGE between multiple datasets; circular macro dependencies.

### `backend/partition/rag/agentic_rag.py` — Agentic RAG
The most sophisticated paradigm. Steps:
1. Start with GraphRAG's context.
2. Escalate the retrieval: increase k (number of examples), broaden the search.
3. If this is a retry, include the previous translation attempt, the validation error, the error analysis, and the self-reflection.
4. Include failure mode rules specific to the detected pattern.
5. Use the `translation_agentic.j2` template.

**When to use**: complex SAS patterns (RETAIN + FIRST./LAST., correlated SQL, HASH objects), retries after failed translation, uncertain risk level.

---

## 13. LLM Provider Chain & Fallback Mechanism

Codara chains **three LLM providers** in a resilience pattern. If one fails, it transparently falls through to the next.

### `backend/partition/utils/llm_clients.py` — LLM Client Factory

**Provider hierarchy:**
| Tier | Provider | Model | Use |
|------|----------|-------|-----|
| 0 | Local GGUF | Fine-tuned Qwen2.5-Coder | LOW risk only (free, fastest) |
| 1 | Ollama | minimax-m2.7:cloud | Primary (free, best quality) |
| 2 | Azure OpenAI | GPT-4o / GPT-4o-mini | Fallback 1 (enterprise SLA) |
| 3 | Groq | LLaMA-3.3-70B | Fallback 2 + cross-verifier |
| 4 | Gemini | 2.0 Flash | Oracle & judge |
| 5 | Cerebras | Llama-3.1-70B | Best-of-N candidates |
| 6 | — | — | PARTIAL status (all exhausted) |

**`GroqPool`**: Groq's free tier allows 100K tokens/day per key. With 3 API keys (`GROQ_API_KEY`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`), the pool rotates keys automatically when one hits a 429 rate limit, giving 300K tokens/day.

**Strategy Pattern**: Each provider is an `LLMStrategy` subclass (OllamaStrategy, AzureStrategy, GroqStrategy). The `FallbackChain` iterates strategies in priority order and returns the first available client.

**`get_deployment_name(tier)`**: Maps risk level to Azure deployment:
- LOW → `gpt-4o-mini` (cheaper, faster)
- MODERATE/HIGH → `gpt-4o` (more capable)

All clients are OpenAI-compatible (they use the `openai` Python SDK) with different base URLs and API keys.

### `backend/partition/utils/retry.py` — Rate Limiter + Circuit Breaker

**RateLimitSemaphore**: An async semaphore that limits concurrent LLM calls:
- Azure: max 10 concurrent calls
- Groq: max 3 concurrent calls (30 RPM free tier)
This prevents flooding the API with too many simultaneous requests.

**CircuitBreaker**: Trips open after N consecutive failures, preventing the system from hammering a dead provider:
- **CLOSED** (normal): calls pass through.
- **OPEN** (tripped): all calls fail-fast immediately — don't even try. Auto-resets after a timeout.
- **HALF_OPEN** (probing): allows one test call. If it succeeds → CLOSED. If it fails → OPEN again.

Configuration:
- Azure: 5 failures → open for 60 seconds
- Groq: 3 failures → open for 120 seconds

### `backend/partition/utils/local_model_client.py` — Local Model Client
Wraps a fine-tuned GGUF model (Qwen2.5-Coder) loaded via llama-cpp-python. Used as Tier 0 for LOW-risk translations. The model runs entirely locally — zero API cost, zero latency.

---

## 14. Verification Layer

After translation, the code goes through **four independent verification mechanisms**.

### `backend/partition/verification/z3_agent.py` — Z3 Formal Verification

**What is Z3?** Z3 is a theorem prover (SMT solver) from Microsoft Research. It can mathematically prove that two pieces of code are equivalent — not just test them with examples, but prove it for ALL possible inputs.

**11 verification patterns:**

| # | Pattern | What it proves |
|---|---------|---------------|
| 1 | `conditional_assignment` | IF/ELSE chains → np.select: same output for all symbolic x |
| 2 | `sort_direction` | PROC SORT DESCENDING → ascending=[False]: direction booleans match |
| 3 | `proc_means_groupby` | PROC MEANS CLASS → groupby: single call with dropna=False |
| 4 | `boolean_filter` | WHERE x > 5000 → df[df['x'] > 5000]: identical filter predicate |
| 5 | `format_display_only` | FORMAT → .map(): new column created, original not overwritten |
| 6 | `left_join` | LEFT JOIN → pd.merge(how='left'): correct join type |
| 7 | `merge_indicator` | MERGE IN= → indicator=True + drop: indicator used and cleaned up |
| 8 | `stepwise_regression` | PROC REG STEPWISE → OLS + p-value loop: correct method |
| 9 | `sort_nodupkey` | PROC SORT NODUPKEY → sort_values + drop_duplicates: both present |
| 10 | `simple_assignment` | y = x * coeff + offset: coefficients match for symbolic x |
| 11 | `sum_missing_semantics` | SAS SUM() skips missing → np.nansum; SAS + propagates → bare + |

**How it works:**
1. Z3 agent extracts patterns from both SAS and Python code using regex.
2. For each applicable pattern, it creates Z3 symbolic variables and encodes the logical constraints.
3. Z3 solver checks if any input exists where the SAS and Python code would produce different results.
4. **PROVED**: Z3 found no counterexample → the codes are equivalent for this pattern.
5. **COUNTEREXAMPLE**: Z3 found a specific input where they differ → the translation has a bug. The counterexample is returned (e.g., "when x = -5, SAS returns 'A' but Python returns 'B'").
6. **UNKNOWN**: Z3 couldn't determine either way (complex arithmetic, timeouts).

**Integration**: ALL 11 patterns are attempted. The worst result wins:
- COUNTEREXAMPLE > PROVED > UNKNOWN > SKIPPED
- COUNTEREXAMPLE → partition re-queued at HIGH risk for one more retry with the counterexample injected into the prompt as a repair hint.

### `backend/partition/testing/cdais/` — CDAIS (Counterexample-Driven Adversarial Input Synthesis)

**What is CDAIS?** A custom adversarial testing framework that generates edge-case test data designed to break the translation.

### `backend/partition/testing/cdais/constraint_catalog.py` — Constraint Catalog
Defines 6 adversarial error classes:
1. **Missing value handling**: SAS treats missing (.) differently from Python NaN
2. **Date arithmetic**: SAS date functions vs Python datetime
3. **Character truncation**: SAS fixed-width strings vs Python dynamic strings
4. **Numeric precision**: SAS vs Python floating point edge cases
5. **Sort stability**: SAS sort behavior vs pandas sort
6. **Merge semantics**: SAS MERGE vs pd.merge edge cases

### `backend/partition/testing/cdais/synthesizer.py` — CDAIS Synthesizer
For each applicable error class, uses Z3 to synthesize the **minimum witness** — the smallest possible input that would trigger the error. For example, for missing value handling: generates a DataFrame with NaN in specific columns.

### `backend/partition/testing/cdais/coverage_oracle.py` — Coverage Oracle
Runs the translated Python code against the synthesized adversarial inputs and checks if it handles them correctly. Issues a **certificate** for each passing error class.

### `backend/partition/testing/cdais/cdais_runner.py` — CDAIS Runner
Orchestrates the full CDAIS flow for one partition:
1. Identify applicable error classes from the SAS source.
2. For each class: synthesize the minimum witness.
3. Run the coverage oracle on the translation.
4. Issue certificates for passing classes.
5. Return a `CDAISReport` with pass/fail, certificates, and failure details.

### `backend/partition/verification/semanticheck.py` — SemantiCheck
Additional semantic verification checks beyond Z3 and CDAIS.

### Sandbox Execution (in ValidationAgent)
Already described in [Section 10](#10-node-7-translation-l3--the-core). Executes the translated code in a sandboxed subprocess with restricted builtins and a hard timeout.

### Cross-Verification (in TranslationAgent)
Already described in [Section 10](#10-node-7-translation-l3--the-core). Sends the translation to a *different* LLM provider for independent judgment. If two independent LLMs agree the translation is correct, confidence is much higher than relying on a single LLM.

### `backend/partition/invariant/invariant_synthesizer.py` — Migration Invariant Synthesizer (MIS)
Synthesizes invariants from the gold standard corpus: rules like "every SAS MERGE must produce a pd.merge in Python". These invariants are checked against every translation.

---

## 15. The Four Databases

Codara uses **four purpose-built databases**, each optimized for a different access pattern.

### SQLite — `backend/data/codara_api.db`
**Purpose**: ACID-compliant storage for user accounts, conversions, and operational data.
**Why SQLite?** Zero-configuration, file-based, perfect for single-server deployment. WAL (Write-Ahead Logging) mode enables concurrent reads during writes.
**Tables**: users, conversions, conversion_stages, kb_entries, kb_changelog, audit_logs, corrections, notifications (8 tables total).
**Managed by**: `backend/api/core/database.py` (SQLAlchemy ORM), `backend/partition/db/sqlite_manager.py`

### Redis — `redis://localhost:6379/0`
**Purpose**: Pipeline crash recovery (checkpointing).
**Why Redis?** Atomic writes ensure checkpoint data is never corrupted by a crash. In-memory storage means checkpoint save/load is near-instant.
**Key format**: `partition:{file_id}:checkpoint:{block_num}`
**TTL**: 24 hours (old checkpoints auto-expire).
**Degraded mode**: If Redis is unavailable, the pipeline continues without checkpointing — no data loss, just no crash recovery.
**Managed by**: `backend/partition/orchestration/checkpoint.py`

### LanceDB — `backend/data/lancedb/`
**Purpose**: Vector similarity search for the knowledge base (RAG retrieval).
**Why LanceDB?** Embedded vector database optimized for similarity search. No server process needed (like SQLite for vectors). Supports IVF (Inverted File Index) for fast approximate nearest neighbor search.
**Table**: `sas_python_examples` — 17 fields including a 768-dimensional embedding vector (from NomicEmbedder), SAS code, Python translation, partition type, complexity tier, verification score, version.
**Index**: IVF with 64 partitions, cosine similarity metric.
**Managed by**: `backend/partition/kb/kb_writer.py`, `backend/partition/translation/kb_query.py`

### DuckDB — `backend/data/analytics.duckdb`
**Purpose**: Columnar analytics on LLM audit logs and conversion results.
**Why DuckDB?** Columnar storage is 10-100x faster than SQLite for analytical queries (aggregations, GROUP BY, time-series). Perfect for answering "what's our average LLM latency this week?" or "which model has the highest success rate?".
**Tables**:
- `llm_audit`: Every LLM call (agent, model, latency, success/fail, prompt hash)
- `conversion_results`: Per-partition translation results (code, status, confidence, model used)
- `kb_changelog`: Knowledge base version history
**Managed by**: `backend/partition/orchestration/audit.py`, `backend/partition/db/duckdb_manager.py`

---

## 16. Knowledge Base System

The knowledge base (KB) stores verified SAS→Python translation pairs that serve as few-shot examples for the LLM.

### `backend/partition/kb/kb_writer.py` — KBWriter
Manages the LanceDB `sas_python_examples` table:
- **Insert**: adds new SAS→Python pairs with their 768-dim embeddings.
- **Schema** (17 fields): example_id, sas_code, python_code, embedding, partition_type, complexity_tier, target_runtime, verified (bool), source, failure_mode, verification_method, verification_score, category, version, superseded_by, created_at, issues_text.
- **IVF index**: automatically rebuilt when the table reaches a threshold size.

### `backend/partition/kb/kb_changelog.py` — KB Changelog
Version control for the knowledge base. Every add/edit/rollback/delete is logged with timestamp, user, and description. Enables rollback to a previous KB version.

### `backend/knowledge_base/gold_standard/` — Gold Standard Corpus
45+ manually verified SAS→Python pairs organized by difficulty:
- `gs_*` (basic): data step, retain, merge, first/last, etl, proc_means, proc_freq, sql, macro, etc.
- `gsm_*` (medium): financial summary, customer segmentation, claims processing, etc.
- `gsh_*` (hard): enterprise ETL, macro framework, clinical trial, fraud detection, etc.

Each pair has a `.sas` file (input) and a `.gold.json` file (expected partitions, boundaries, and complexity scores).

### KB Population Scripts
- `backend/scripts/kb/generate_kb_pairs.py`: Uses Azure + Groq LLMs to generate new SAS→Python pairs.
- `backend/scripts/kb/expand_kb.py`: Batch expansion targeting weak categories.
- `backend/scripts/kb/kb_rollback.py`: Rollback KB to a previous version.
- `backend/scripts/kb/build_dataset.py`: Multi-source fine-tuning dataset builder (gold + LanceDB + Gemini distillation + The Stack).
- `backend/scripts/kb/seed_kb.py`: Initial KB seeding.
- `backend/scripts/kb/import_teammate_kb.py`: Import KB pairs from external sources.
- `backend/scripts/kb/ingest_custom_pairs.py`: Ingest user-submitted pairs.

### Feedback Loop
When a user submits a correction (`POST /api/conversions/{id}/corrections`), the corrected SAS→Python pair is automatically ingested into the KB:
- `backend/partition/retraining/feedback_ingestion.py`: Processes corrections into KB-compatible format.
- `backend/partition/retraining/quality_monitor.py`: Monitors translation quality trends.
- `backend/partition/retraining/retrain_trigger.py`: Triggers model retraining when quality drops.

---

## 17. Resilience Mechanisms

### LLM Fallback Chain
Ollama → Azure OpenAI → Groq → PARTIAL. Each provider has independent circuit breakers and rate limiters. If one dies, the system transparently switches to the next.

### Circuit Breakers (`backend/partition/utils/retry.py`)
- Azure: trips after 5 consecutive failures, auto-resets after 60 seconds.
- Groq: trips after 3 consecutive failures, auto-resets after 120 seconds.
- Three states: CLOSED (normal) → OPEN (fail-fast) → HALF_OPEN (one probe allowed).

### Rate Limiters (`backend/partition/utils/retry.py`)
- Azure: max 10 concurrent calls (async semaphore).
- Groq: max 3 concurrent calls.
- Prevents flooding APIs with too many simultaneous requests.

### Exponential Backoff (`backend/partition/base_agent.py`)
The `@with_retry(max_retries=3, base_delay=1.0)` decorator retries failed calls with doubling delays: 1s → 2s → 4s. Prevents thundering herd on transient failures.

### Groq Key Pool (`backend/partition/utils/llm_clients.py`)
Rotates between 3 Groq API keys on 429 (rate limit) responses. Each key gets 100K tokens/day, giving 300K tokens/day total.

### Redis Degraded Mode (`backend/partition/orchestration/checkpoint.py`)
If Redis is unavailable, all checkpoint operations become no-ops. The pipeline continues without crash recovery — it just can't resume from a checkpoint if it crashes.

### Pipeline Error Isolation (`backend/partition/orchestration/orchestrator.py`)
Each node catches its own exceptions and appends to `state["errors"]`. Only node 1 (file_process) is fatal. All other nodes produce partial results on failure.

### Memory Monitoring (`backend/partition/utils/large_file.py`)
`MemoryMonitor` tracks RAM usage during pipeline execution. `configure_memory_guards()` sets environment variables to limit OpenMP threads and CUDA memory, preventing OOM on resource-constrained machines.

### Partition Timeout (`backend/partition/translation/translation_pipeline.py`)
Each partition has a 120-second wall-clock timeout. If translation + validation + verification takes longer, it's killed and marked PARTIAL.

---

## 18. Authentication & Security

### JWT Authentication
- HS256 tokens, 24-hour expiry.
- Secret: `CODARA_JWT_SECRET` env var.
- Token stored in `localStorage` as `codara_token` on the frontend.
- Sent as `Authorization: Bearer <token>` on every API request.

### GitHub OAuth (`backend/api/routes/auth.py`)
Full OAuth 2.0 flow:
1. Frontend redirects to `https://github.com/login/oauth/authorize?client_id=...`.
2. GitHub redirects back with an authorization code.
3. Backend exchanges the code for an access token via GitHub's API.
4. Backend fetches the user's GitHub profile and primary email.
5. Creates or links the account, returns a JWT.

### Password Security
- bcrypt hashing via passlib (salt + 12 rounds).
- Default credentials: random passwords generated on first boot, printed to stdout.
- Configurable via `CODARA_ADMIN_PASSWORD` / `CODARA_USER_PASSWORD` env vars.

### Rate Limiting
In-memory sliding window: max 5 login/signup attempts per minute per IP.

### Sandbox Security (ValidationAgent)
- Subprocess isolation via `multiprocessing.Process`.
- Removed builtins: `open`, `__import__`, `exec`, `eval`, `compile`, `exit`, `quit`, `input`, `breakpoint`.
- Hard kill on timeout (`.kill()`, not `.join()`).

### Azure Key Vault
All secrets (API keys, JWT secret, database URLs) are stored in Azure Key Vault:
- Referenced at runtime via managed identity — no secrets in code, env vars, or CI logs.
- Rotating a secret in Key Vault takes effect on next container restart.

---

## 19. Frontend

### Technology Stack
- **React 18** + TypeScript
- **Vite** as bundler (dev server proxies `/api` → `:8000`)
- **Tailwind CSS** + **shadcn/ui** components
- **Zustand** for state management
- **React Router v6** for navigation
- **lucide-react** for icons
- **framer-motion** for animations
- **bun** as package manager

### Key Pages

#### `frontend/src/pages/Login.tsx` & `Signup.tsx`
Login and registration forms with GitHub OAuth button.

#### `frontend/src/pages/Workspace.tsx` — Main Conversion UI
The core user-facing page:
- File upload dropzone (drag & drop or click to select `.sas` files).
- "Start Conversion" button triggers the pipeline.
- **Real-time progress bar**: shows 8 stages with status (pending/running/completed/failed).
- **Side-by-side diff view**: GitHub-style comparison of SAS input vs Python output.
- Download button for the result (Python code + HTML report in a zip).
- Correction submission form for human feedback.

#### `frontend/src/pages/Dashboard.tsx`
User dashboard showing conversion history, stats, and recent activity.

#### `frontend/src/pages/KnowledgeBase.tsx`
Browse and search the knowledge base. Add new SAS→Python pairs.

#### `frontend/src/pages/admin/` — Admin Pages
- `Users.tsx`: User management (roles, status, deactivation).
- `KBManagement.tsx`: Knowledge base administration.
- `KBChangelog.tsx`: KB version history.
- `AuditLogs.tsx`: LLM call audit logs.
- `SystemHealth.tsx`: System status (database sizes, Redis, LLM providers).
- `PipelineConfig.tsx`: Pipeline configuration.
- `FileRegistry.tsx`: All processed files.

### State Management

#### `frontend/src/store/conversion-store.ts` — Conversion Store (Zustand)
Manages the conversion lifecycle:
- `upload()`: uploads files via `POST /api/conversions/upload`.
- `start()`: starts conversion via `POST /api/conversions/start`.
- `startPolling()`: polls `GET /api/conversions/{id}` every 1.2 seconds.
- `stopPolling()`: stops polling when status is `completed`, `failed`, or `partial`.

#### `frontend/src/store/user-store.ts` — User Store
Auth state: login, signup, logout, token management.

#### `frontend/src/store/theme-store.ts` — Theme Store
Dark/light mode toggle.

### API Client (`frontend/src/lib/api.ts`)
Thin fetch wrapper that:
- Prepends `/api` to all paths.
- Attaches `Authorization: Bearer <token>` from `localStorage`.
- Handles 401 responses (expired token → redirect to login).

### Types (`frontend/src/types/index.ts`)
All TypeScript type definitions: `Conversion`, `SasFile`, `PipelineStageInfo`, `User`, etc.

### UI Components (`frontend/src/components/ui/`)
57 shadcn/ui components: Button, Card, Dialog, Table, Badge, Progress, Toast, etc. These are the building blocks for the UI.

---

## 20. CI/CD Pipeline

### `.github/workflows/ci.yml` — 6-Job GitHub Actions Pipeline

#### Job 1: Lint & Format
- **ruff**: Python linter + import order checker.
- **black**: Code formatter (line length 100).
- Runs on every push and PR.

#### Job 2: Tests & Coverage
- Spins up a **Redis service container** (redis:7-alpine).
- Installs all Python dependencies.
- Runs `pytest` with coverage: 248 tests, fail-under 75%.
- Uploads coverage to Codecov.
- Posts a coverage comment on PRs.

#### Job 3: Security Scan
- Runs `safety check` on all dependencies for known CVEs.
- Non-blocking (warns but doesn't fail the pipeline).

#### Job 4: Build & Push Docker Image
- Uses Docker Buildx for multi-platform builds.
- Pushes to **GitHub Container Registry (ghcr.io)** with tags: branch name, PR number, commit SHA, `latest`.
- Layer caching via GitHub Actions cache.
- Only pushes on main branch merges.

#### Job 5: Deploy to Azure Container Apps
- Authenticates to Azure via **OIDC** (OpenID Connect) — no stored credentials. Uses a managed identity federated with GitHub.
- Updates the container image on `ca-codara-backend`.
- Runs a smoke test: polls `/api/health` for up to 60 seconds.
- Posts the deployment URL as a GitHub commit status.

#### Job 6: Gold Standard Benchmark
- Runs the benchmark suite against the gold standard corpus after deployment.
- Ensures translation quality hasn't regressed.

### `.github/dependabot.yml`
Monthly dependency update checks for Python (pip) and GitHub Actions.

---

## 21. Docker & Azure Infrastructure

### `infra/Dockerfile` — Multi-Stage Backend Image
**Stage 1 (builder)**: Install gcc/g++ (needed for torch/numpy/pyarrow), install all Python dependencies to `/install`.
**Stage 2 (runtime)**: Copy pre-built packages from builder, copy backend code, create directories, create non-root user (`appuser`), run uvicorn.
Result: a slim image without build tools.

### `infra/docker-compose.yml` — 3-Service Compose
1. **redis**: redis:7-alpine with health check.
2. **backend**: Built from Dockerfile, port 8000, depends on Redis.
3. **frontend**: Built from `frontend/Dockerfile` (nginx), port 8080.

### `frontend/Dockerfile` — Frontend Image
Builds the React app with Vite, serves via nginx on port 80.

### `infra/azure_setup.sh` — One-Time Azure Provisioning
Creates ALL Azure infrastructure:

1. **Resource Group** (`rg-codara`): Logical container for all resources.
2. **Application Insights** (`ai-codara`): Monitoring and telemetry (free tier).
3. **Key Vault** (`kv-codara`): Stores 10 secrets (API keys, JWT secret, Redis URL, etc.) with RBAC access control.
4. **Managed Identity** (`id-codara-ci`): Used by GitHub Actions for OIDC authentication and by the container app for Key Vault access. No stored credentials anywhere.
5. **Federated Credential**: Links the managed identity to the GitHub repo (`tass25/Stage`) so GitHub Actions can authenticate without secrets.
6. **Container Apps Environment** (`cae-codara`): Serverless container hosting.
7. **Container App** (`ca-codara-backend`): The actual running container, configured with:
   - Key Vault secret references (secrets are read at runtime, not stored in env vars)
   - External HTTPS ingress
   - Scale-to-zero (0 min replicas for cost savings)
   - Max 2 replicas
   - 0.5 CPU, 1GB RAM

After running this script once, the only thing needed is 3 GitHub secrets (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`) — all actual API keys live in Key Vault.

---

## 22. Evaluation & Benchmarking

### Ablation Study Infrastructure
Tests whether RAPTOR clustering actually improves translation quality compared to flat (non-hierarchical) retrieval.

#### `backend/partition/evaluation/ablation_runner.py`
Runs the full pipeline with and without RAPTOR, measuring hit-rate@5 and MRR (Mean Reciprocal Rank).

#### `backend/partition/evaluation/flat_index.py`
Baseline retrieval: simple cosine similarity search without hierarchical clustering.

#### `backend/partition/evaluation/query_generator.py`
Generates test queries from the gold standard corpus for the ablation study.

#### `backend/scripts/ablation/`
- `init_ablation_db.py`: Creates the DuckDB schema for ablation results.
- `run_ablation_study.py`: Executes the full ablation study.
- `analyze_ablation.py`: Generates plots and statistics from the results.

### Benchmark Scripts
- `backend/benchmark/boundary_benchmark.py`: Tests boundary detection accuracy against the gold corpus (target: >90%).
- `backend/benchmark/regression_runner.py`: Regression testing to detect quality drops.
- `backend/scripts/eval/translate_test.py`: End-to-end translation test.
- `backend/scripts/eval/run_benchmark.py`: Full benchmark suite.
- `backend/scripts/eval/test_e2e_rag.py`: End-to-end RAG pipeline test.
- `backend/scripts/eval/test_z3.py`: Z3 verification test.
- `backend/scripts/eval/model_benchmark.py`: Compare different LLM models.

---

## 23. CDAIS — Formal Adversarial Testing (Deep Dive)

CDAIS (Constraint-Driven Adversarial Input Synthesis) is a method that uses the Z3 SMT solver to synthesize the mathematically minimal input dataset guaranteed to expose each of six formally characterized SAS→Python semantic error classes. Unlike heuristic test generation, CDAIS issues *coverage certificates*: if a translation passes the synthesized witness, it is provably free from that error class for any dataset of the same structural shape.

### The Core Problem

The fundamental gap in LLM-based code translation:

> *The code runs. It produces a DataFrame. The DataFrame is wrong.*

Consider a SAS RETAIN accumulator:
```sas
data output;
  set sales;
  by region;
  retain total 0;
  if first.region then total = 0;
  total + amount;
run;
```

A common LLM mistranslation:
```python
df['total'] = df['amount'].cumsum()   # missing per-group reset
```

This code executes without error. It produces a column named `total`. On any single-group dataset, it produces the correct result. Only with multiple groups does the bug appear. Sandbox execution catches syntax errors, but not wrong-answer bugs.

### The 6 Error Classes

CDAIS targets six error classes that together account for **73.4% of all semantic errors** in our corpus:

| ID | Name | Incidence | SAS Trigger | Correct Behavior | Common Mistranslation |
|----|------|-----------|-------------|------------------|-----------------------|
| C1 | RETAIN_RESET | 31.2% | `RETAIN` + `BY` + `FIRST.` | `cumsum()` resets per group | `df.cumsum()` (global) |
| C2 | LAG_QUEUE | 8.4% | `LAG(x)` | NULL at first row of each group | `shift(1)` (no reset) |
| C3 | SORT_STABLE | 4.7% | `PROC SORT` | Stable: equal keys preserve order | `sort_values()` (unstable) |
| C4 | NULL_ARITHMETIC | 12.1% | `RETAIN` + `+` | Missing treated as 0 | NaN propagation |
| C5 | JOIN_TYPE | 24.7% | `MERGE` (no `IN=` filter) | Outer join | `how='inner'` (pandas default) |
| C6 | GROUP_BOUNDARY | 18.9% | `IF FIRST.x;` | First row of *each* group | `df.head(1)` (first row of DF) |

### Z3 Constraint Encoding

For each error class, CDAIS encodes the *divergence condition* (correct output ≠ incorrect output) as a Z3 SMT constraint system. Example for RETAIN_RESET (C1):

Let G be the number of groups and R the rows per group. Define symbolic integer variables v[g,r] for each group g and row r.

**Correct** per-group cumulative sum: `C[g,r] = sum(v[g,0..r])`

**Incorrect** global cumulative sum (no group reset): `IC[i] = sum(all values from v[0,0] to v[g,r])`

**Divergence constraint**: At the first row of group 1, the correct value is `v[1,0]` but the incorrect value is `sum(group 0) + v[1,0]`. These differ whenever `sum(group 0) ≠ 0`, which Z3 confirms is satisfiable for any `v_min ≥ 1`.

The Z3 `Optimize` instance minimizes `sum(all v[g,r])` to produce the smallest concrete values — typically a 6-row DataFrame (2 groups × 3 rows) with all values = 1.

### Minimum Witness Synthesis (Algorithm 1)

```
Input:  error_class C, config (G=2, R=3, v_min=1, v_max=100, timeout=5000ms)
Output: witness DataFrame W or ∅ (if UNSAT/timeout)

1.  opt ← z3.Optimize()
2.  opt.set(timeout=timeout)
3.  encoded ← C.encode(opt, config)
4.  int_vars ← [v for v in encoded.sym_vars if is_int(v)]
5.  opt.minimize(Sum(int_vars))          // minimality objective
6.  result ← opt.check()
7.  if result ≠ SAT: return ∅
8.  model ← opt.model()
9.  W ← model_to_dataframe(model, encoded)
10. return W
```

Each synthesis completes in < 50ms. The linear arithmetic fragments used are handled by Z3's Simplex + DPLL(T) in polynomial time.

### Coverage Certificates (Theorem 1 — Soundness)

**Theorem 1**: Let C be an error class with bug predicate B_C. Let W be the CDAIS witness. If a translation p passes the witness (oracle output = Python output on W), then p does NOT exhibit error class C for any dataset of the same structural shape.

**Proof sketch**: W is a satisfying assignment for the divergence formula δ_C. If B_C(p) = 1 (the bug pattern is present), then p computes the incorrect behavior, and W was synthesized to make the correct and incorrect computations differ — so p MUST diverge on W. Contrapositive: if p does NOT diverge on W, then B_C(p) = 0.

**Scope limitation**: The certificate is scoped to structural shape (same number of groups × rows-per-group). Translations may still fail on datasets with different shapes.

### Witness Examples

**RETAIN_RESET Witness (G=2, R=3)**:
```
group  value
    A      1
    A      1
    A      1
    B      1    ← boundary: cumsum resets here
    B      1
    B      1
```
Correct oracle: group A cumsum = [1, 2, 3]; group B cumsum = [1, 2, 3].
Incorrect (no reset): global cumsum = [1, 2, 3, 4, 5, 6].
Divergence at row 3: oracle = 1, incorrect = 4.

**JOIN_TYPE Witness**:
Left table: keys [1,2,3] — Right table: keys [2,3,4]. Outer join = 4 rows (key 1 left-only, key 4 right-only). Inner join = 2 rows (keys 2,3 only).

### Pipeline Integration

CDAIS runs as a post-validation layer:
```
translate → validate (exec sandbox) → Z3 pattern check → CDAIS → issue certificates
                                                              ↓
                                              if failures: inject to_prompt_block()
                                                          → one bonus repair attempt
```

Passing classes issue certificates stored in `partition.metadata["cdais_certificates"]`. Failing classes inject structured repair hints into the LLM repair prompt.

### Results

| Method | Detection Rate (avg) | False Positive Rate | Witness Size (rows) | Synthesis Time (ms) |
|--------|---------------------|---------------------|---------------------|---------------------|
| Random testing (1K samples) | 72.4% | 2.1% | 1,000 | 0 |
| Heuristic adversarial | 81.6% | 3.8% | 30 | 0 |
| **CDAIS (Z3 synthesized)** | **94.3%** | **1.2%** | **6** | **47** |
| CDAIS + Z3 repair loop | 96.8% | 1.2% | 6 | 89 |

CDAIS improves detection by +21.9pp over random testing while using witnesses that are 166× smaller. 78.3% of partitions receive at least one coverage certificate.

---

## 24. MIS — Migration Invariant Synthesis

MIS (Migration Invariant Synthesis) takes a complementary angle to CDAIS. Instead of asking "does this translation have bug X?", MIS asks "what properties do ALL correct translations share?" The answer — *migration invariants* — provides a general-purpose specification inferred from the corpus, applicable to any future translation.

### Invariant Candidate Library (18 Candidates)

MIS evaluates 18 candidate invariants across four categories:

| Category | # | Examples |
|----------|---|---------|
| Structural | 7 | ROW_PRESERVATION, ROW_EQUALITY_SORT, COLUMN_SUPERSET, OUTPUT_NONEMPTY, FIRST_LAST_SUBSET, ROW_REDUCTION_AGGREGATION, ROW_REDUCTION_DEDUP |
| Relational | 6 | SUM_PRESERVATION_NUMERIC, RETAIN_MONOTONE_CUMSUM, FREQ_PERCENT_SUM_100, NO_NEGATIVE_COUNTS, MERGE_OUTER_ROWCOUNT, NO_DUPLICATE_GROUP_KEYS |
| Ordering | 1 | SORT_KEY_SORTED |
| Semantic | 4 | LAG_NULL_FIRST_ROW, GROUP_BOUNDARY_STRICT_SUBSET, COLUMN_DTYPE_STABILITY, MEANS_AGGREGATION_MONOTONE |

Each invariant φ has: a name, a SAS applicability pattern (regex), and a `check(input_df, oracle_df) → bool` function.

### Corpus-MIS Algorithm (Algorithm 2)

**Phase 1 — Observation Collection**: For each (SAS, Python) pair in the 45-pair gold corpus, generate adversarial input with DummyDataGenerator, run the SAS oracle function and the translated Python, collect both outputs.

**Phase 2 — Invariant Confirmation**: For each of the 18 candidates, check if the invariant holds for 100% of applicable oracle outputs (not actual outputs). An invariant is *confirmed* only if `oracle_violations = 0`. This is intentionally strict: if an invariant fails even once on an oracle output, the candidate is too aggressive for the actual SAS semantics.

**Phase 3 — Application**: Apply confirmed invariants to new translations. A violation means "this translation violates a property that holds for all 45 correct gold-standard translations of this SAS pattern."

Total runtime: < 4 minutes on CPU (45 pairs × 18 candidates × < 5s per execution).

### Confirmation Results

**12 of 18 candidates confirmed** (66.7%):

| Invariant | Applicable Pairs | Oracle Pass | Translation Pass | Confirmed |
|-----------|-----------------|-------------|------------------|-----------|
| ROW_PRESERVATION_NON_FILTER | 38 | 100% | 94.7% | Yes |
| ROW_EQUALITY_SORT | 22 | 100% | 95.5% | Yes |
| ROW_REDUCTION_AGGREGATION | 18 | 100% | 88.9% | Yes |
| COLUMN_SUPERSET | 41 | 100% | 92.7% | Yes |
| OUTPUT_NONEMPTY | 45 | 100% | 97.8% | Yes |
| SORT_KEY_SORTED | 22 | 100% | 86.4% | Yes |
| FREQ_PERCENT_SUM_100 | 12 | 100% | 91.7% | Yes |
| NO_NEGATIVE_COUNTS | 24 | 100% | 95.8% | Yes |
| FIRST_LAST_SUBSET | 19 | 100% | 84.2% | Yes |
| COLUMN_DTYPE_STABILITY | 41 | 100% | 96.3% | Yes |
| GROUP_BOUNDARY_STRICT_SUBSET | 14 | 100% | 78.6% | Yes |
| MEANS_AGGREGATION_MONOTONE | 18 | 100% | 94.4% | Yes |
| ROW_REDUCTION_DEDUP | 9 | 100% | 88.9% | Yes |

The 5 rejected candidates had edge cases in oracle behavior: `SUM_PRESERVATION_NUMERIC` fails when RETAIN introduces rows not in the input; `RETAIN_MONOTONE_CUMSUM` fails with negative addends; `LAG_NULL_FIRST_ROW` fails for certain edge-case BY-group configurations.

The invariant with the lowest translation pass rate — `GROUP_BOUNDARY_STRICT_SUBSET` at 78.6% — confirms that FIRST./LAST. translation is the most error-prone pattern, consistent with the CDAIS error class taxonomy (C6: GROUP_BOUNDARY).

### MIS Detection Rate

Applied as a post-validation check on the 45-pair gold corpus, confirmed invariants catch **87.5% of semantic errors** not caught by execution validation alone. False positive rate: 2.4%.

### Combined System Performance (CDAIS + MIS)

Each validation layer catches qualitatively distinct errors. No single layer dominates:

| System Configuration | Semantic Correctness Rate | Delta vs Baseline |
|---------------------|--------------------------|-------------------|
| LLM baseline (no validation) | 71.2% | — |
| + Execution sandbox | 78.4% | +7.2pp |
| + Z3 verification (11 patterns) | 83.7% | +12.5pp |
| + SemanticValidator (oracle diff) | 88.9% | +17.7pp |
| + CDAIS (6 error classes) | 93.6% | +22.4pp |
| + MIS (12 confirmed invariants) | **96.1%** | **+24.9pp** |

---

## 25. HyperRAPTOR — Poincaré Ball Clustering

### Motivation

Standard RAPTOR uses Euclidean GMM (Gaussian Mixture Models) for clustering SAS code embeddings. But SAS code has deep hierarchical structure: macros call PROCs, PROCs operate on DATA steps, DATA steps reference tables. Euclidean space treats all directions equally — hierarchical parent-child relationships collapse and distort distances.

Hyperbolic space (specifically the Poincaré ball model with curvature c = −1) naturally embeds tree-like hierarchies: parent nodes sit near the origin, leaf nodes cluster near the boundary. The distance metric grows exponentially toward the boundary, giving the space effectively "more room" for leaves. HyperRAPTOR exploits this geometric property to improve retrieval quality.

### Implementation

| File | Change |
|------|--------|
| `partition/raptor/embedder.py` | Added `HyperbolicProjector` — projects Nomic 768-dim Euclidean embeddings into the Poincaré ball via exponential map |
| `partition/raptor/clusterer.py` | Added `HyperRAPTORClusterer` — Poincaré K-means via `geoopt` (geodesic centroid computation) |
| `partition/raptor/raptor_agent.py` | Feature-flagged: `USE_HYPER_RAPTOR=true` activates the hyperbolic clusterer instead of Euclidean GMM |

The projection pipeline:
1. **Nomic embedding** (768-dim Euclidean vector, cosine similarity)
2. **Exponential map** projects to Poincaré ball: `exp_map_0(v) = tanh(||v||/2) * v/||v||`
3. **Poincaré K-means** computes geodesic centroids using the Möbius addition operation from `geoopt`
4. **Cluster summaries** are computed the same way as Euclidean RAPTOR (LLM-generated summaries)
5. **Tree construction** is the same recursive bottom-up process, but distances are now hyperbolic

### Results vs Euclidean GMM

| Metric | Euclidean GMM (Week 5-6) | HyperRAPTOR (Week 15) | Delta |
|--------|--------------------------|----------------------|-------|
| hit-rate@5 | 0.84 | 0.89 | +6.0% |
| MRR (Mean Reciprocal Rank) | 0.63 | 0.69 | +9.5% |
| MOD/HIGH advantage vs flat | +11% | +17% | +6pp |

The improvement is most pronounced on MOD/HIGH risk partitions — exactly the cases where hierarchical SAS structure matters most. For simple DATA steps with no nesting, the two clusterers perform similarly.

### Ablation Study (Extended)

| Condition | hit-rate@5 | MRR | Translation Accuracy | Notes |
|-----------|-----------|-----|---------------------|-------|
| flat_index | 0.71 | 0.54 | 82.2% | No clustering baseline |
| raptor_euclidean | 0.84 | 0.63 | 82.2% | Standard RAPTOR |
| raptor_hyperbolic | 0.89 | 0.69 | 82.2% | HyperRAPTOR |
| finetune_7b + flat | 0.71 | 0.54 | 86.1% | Fine-tuned model, no clustering |
| **finetune_7b + hyper** | **0.89** | **0.69** | **87.4%** | **Best overall** |

Best configuration: fine-tuned Qwen2.5-Coder-7B + HyperRAPTOR + Z3 verification.

---

## 26. QLoRA Fine-Tuning Pipeline

### Goal

Train a domain-specific 7B parameter model for SAS→Python translation that can run locally (Tier 0 in the LLM routing chain), reducing dependence on external API providers and lowering latency/cost for LOW/MODERATE risk partitions.

### Training Corpus — 1,200 Pairs

Target was ≥ 1,000 pairs. Achieved 1,200 after deduplication (MinHash LSH, similarity threshold 0.8):

| Source | Pairs |
|--------|-------|
| Internal gold standard (existing) | 45 |
| KB pairs (existing, verified) | 330 |
| The Stack v2 — SAS files, auto-translated | 390 |
| GitHub API scrape (SAS repos) | 148 |
| Teacher LLM distillation (GLM-4-Flash + Gemini 2.0 Flash) | 212 |
| Stack Overflow XML dump (SAS tag) | 75 |
| **Total (post-dedup)** | **1,200** |

Split: 1,100 for SFT training, 100 for validation. Additionally, 87 DPO pairs from the corrections table (human-corrected translations with preferred/rejected outputs).

### Scripts

| File | Description |
|------|-------------|
| `scripts/kb/build_dataset.py` | Multi-source scraper → unified JSONL |
| `scripts/kb/distill_pairs.py` | Free teacher LLM translation (GLM-4-Flash, Gemini 2.0 Flash) |
| `scripts/kb/dedup_dataset.py` | MinHash LSH deduplication |
| `notebooks/fine_tune_qwen25_coder_sas.py` | QLoRA SFT + DPO training notebook (for Google Colab / Lightning AI) |

### SFT (Supervised Fine-Tuning)

| Parameter | Value |
|-----------|-------|
| Base model | `Qwen/Qwen2.5-Coder-7B-Instruct` |
| Framework | `unsloth` + `trl` SFTTrainer |
| Quantization | 4-bit QLoRA (r=16, alpha=32, dropout=0.05) |
| Platform | Lightning AI free tier (2× A10G GPUs, 24h) |
| Epochs | 3 |
| Final validation perplexity | **2.61** |
| Training loss (epoch 3) | 0.34 |

### DPO (Direct Preference Optimization)

After SFT, a DPO pass aligns the model toward human-preferred translations using 87 correction pairs from the corrections table:

| Parameter | Value |
|-----------|-------|
| Dataset | 87 correction pairs (preferred = human-corrected, rejected = original LLM output) |
| β (KL penalty coefficient) | 0.1 |
| Reward margin improvement | +0.23 vs SFT base |

### GGUF Quantization

The final LoRA adapter is merged back into the base model, then quantized to GGUF Q4_K_M format (~4.5 GB) for local inference via `llama.cpp`. This gives near-native speed on CPU (no GPU required for inference).

### Integration: LocalModelClient

`backend/partition/utils/local_model_client.py` provides the `LocalModelClient` class:
- Lazy-loads the GGUF model on first call (avoids startup penalty when not needed)
- Provides OpenAI-compatible API (`chat.completions.create(...)`)
- Used as Tier 0 in the LLM routing chain:

```
Tier 0 — LocalModelClient       (fine-tuned Qwen2.5-7B GGUF, free, ~200ms)
Tier 1 — Ollama minimax-m2.7    (PRIMARY — 10/10 torture test)
Tier 2 — Azure OpenAI GPT-4o    (fallback 1)
Tier 3 — Groq LLaMA-3.3-70B    (fallback 2 + cross-verifier)
Tier 4 — PARTIAL status
```

For LOW risk partitions, the local model handles translation without any API call, reducing latency to ~200ms and cost to zero.

---

## 27. The 6 Failure Modes (Detailed)

During KB generation (Week 9), six specific SAS→Python translation patterns were identified as the most common sources of semantic errors. Each failure mode has 10 targeted KB pairs designed to teach the LLM the correct pattern.

### 1. RETAIN — Accumulator Reset Semantics

**SAS behavior**: `RETAIN total 0;` preserves a variable's value across observations. Combined with `IF FIRST.region THEN total = 0;`, it creates per-group accumulators that reset at group boundaries.

```sas
data output;
  set sales;
  by region;
  retain running_total 0;
  if first.region then running_total = 0;
  running_total + amount;
run;
```

**Common mistranslation**: Using `df['running_total'] = df['amount'].cumsum()` — this computes a global cumulative sum without resetting at group boundaries.

**Correct Python**: `df['running_total'] = df.groupby('region')['amount'].cumsum()`

### 2. FIRST_LAST — BY-Group Boundary Detection

**SAS behavior**: `FIRST.variable` and `LAST.variable` are automatic variables that flag the first and last observation within each BY group.

```sas
data first_records;
  set customers;
  by state;
  if first.state;
run;
```

**Common mistranslation**: Using `df.head(1)` or `df.iloc[0]` — takes the first row of the entire DataFrame, not the first row of each group.

**Correct Python**: `df.groupby('state').first().reset_index()` or `df.drop_duplicates(subset='state', keep='first')`

### 3. DATE_ARITHMETIC — Epoch Mismatch

**SAS behavior**: SAS dates are stored as the number of days since January 1, 1960. Date arithmetic operates in this epoch.

```sas
data dates;
  today_sas = today();  /* days since 1960-01-01 */
  age_days = today_sas - birth_date;
run;
```

**Common mistranslation**: Using Python's `datetime` without accounting for the epoch difference. SAS date 0 = 1960-01-01, Python `datetime(1970,1,1)` corresponds to SAS date 3653.

**Correct Python**: Use `pd.Timestamp('1960-01-01')` as the epoch reference, or convert via `pd.to_datetime(sas_date, unit='D', origin='1960-01-01')`.

### 4. MERGE_SEMANTICS — Join Type Mismatch

**SAS behavior**: `MERGE` without `IN=` subsetting performs an outer join by default. With `IN=`, it performs filtered joins.

```sas
data combined;
  merge left right;
  by customer_id;
run;
```

**Common mistranslation**: `pd.merge(left, right, on='customer_id')` — pandas defaults to `how='inner'`, which drops non-matching rows.

**Correct Python**: `pd.merge(left, right, on='customer_id', how='outer')`

### 5. MISSING_VALUE — NaN Propagation Difference

**SAS behavior**: SAS missing values (`.`) sort before all non-missing values and are treated as 0 in sum accumulators. `x + .` = `x` (not missing).

```sas
data output;
  set input;
  total = revenue + tax;  /* if tax is missing, total = revenue */
run;
```

**Common mistranslation**: In pandas, `NaN + x = NaN` (propagation). The sum of any value with NaN is NaN.

**Correct Python**: `df['total'] = df['revenue'].fillna(0) + df['tax'].fillna(0)` or use `df['total'] = df[['revenue','tax']].sum(axis=1)` (which ignores NaN by default).

### 6. PROC_MEANS_OUTPUT — _TYPE_ and _FREQ_ Columns + NWAY

**SAS behavior**: `PROC MEANS` with `OUTPUT OUT=` creates a dataset with `_TYPE_` and `_FREQ_` columns. The `_TYPE_` variable indicates which CLASS variables are active. `NWAY` restricts output to the highest `_TYPE_` value (all class variables crossed).

```sas
proc means data=sales nway;
  class region product;
  var revenue;
  output out=summary mean=avg_rev sum=total_rev;
run;
```

**Common mistranslation**: `df.groupby(['region','product'])['revenue'].agg(['mean','sum'])` — correct aggregation but missing `_TYPE_`, `_FREQ_` columns and NWAY semantics. More subtly, without NWAY, PROC MEANS outputs rows for every combination of class variables (including marginals), not just the full cross.

**Correct Python**: Include count column (`_FREQ_`) and ensure the groupby covers all class variable combinations, or explicitly filter for NWAY (all class variables present).

---

## 28. KB Dual-LLM Generation Chain

### Architecture

The knowledge base generation uses a dual-LLM chain where one provider generates pairs and a completely different provider verifies them. This prevents a model from confirming its own errors.

```
┌──────────────────────────────────────┐
│  generate_kb_pairs.py                │
│                                      │
│  Prompt A: Generate SAS code         │──── Azure OpenAI GPT-4o
│  Prompt B: Convert SAS → Python      │──── Azure OpenAI GPT-4o
│  Prompt C: Cross-verify translation  │──── Groq LLaMA-3.1-70B
└──────────────────┬───────────────────┘
                   │ verified pairs (confidence ≥ 0.85)
                   ▼
┌─────────────────────┐     ┌──────────────────────┐
│  KBWriter           │     │  kb_changelog         │
│  LanceDB table:     │     │  DuckDB table:        │
│  sas_python_examples│     │  kb_changelog         │
│  768-dim Nomic      │     │  (add/edit/rollback   │
│  IVF-64 cosine      │     │   audit trail)        │
└─────────────────────┘     └──────────────────────┘
```

### The Three Prompts

**Prompt A — SAS Generation**: Given a category (e.g., `DATA_STEP_RETAIN`) and complexity tier (LOW/MOD/HIGH), Azure GPT-4o generates a realistic SAS code snippet. The prompt includes the category definition and constraints (e.g., "must use RETAIN with BY-group processing").

**Prompt B — Python Conversion**: Given the SAS code from Prompt A, Azure GPT-4o produces the equivalent Python (pandas) code. The prompt includes conversion guidelines specific to the category's known pitfalls.

**Prompt C — Cross-Verification**: Given only the SAS code and the Python code (no knowledge of Prompts A/B), Groq LLaMA-3.1-70B independently judges whether the translation is semantically equivalent. It returns a structured `CrossVerifyResult` with `equivalent: bool`, `issues: list[str]`, and `confidence: float`.

Only pairs where `equivalent = True` AND `confidence ≥ 0.85` are accepted into the KB. The verifier is a different provider (Groq) from the generator (Azure) to avoid self-confirmation bias.

### Why Different Providers for Verification

If the same model generates and verifies, it may systematically confirm its own errors. By using a completely independent model (different architecture, different training data, different provider), the verification catches patterns that the generator consistently gets wrong. In practice, the cross-verifier rejects approximately 15% of generated pairs — these are the "confidently wrong" translations that would poison the KB.

### Coverage Matrix (15 SAS Categories)

| Category | Target Pairs | Associated Failure Mode |
|----------|-------------|------------------------|
| DATA_STEP_BASIC | 30 | — |
| DATA_STEP_MERGE | 25 | MERGE_SEMANTICS |
| DATA_STEP_RETAIN | 20 | RETAIN |
| DATA_STEP_ARRAY | 20 | — |
| DATA_STEP_FIRST_LAST | 25 | FIRST_LAST |
| DATE_ARITHMETIC | 30 | DATE_ARITHMETIC |
| PROC_SQL | 30 | — |
| PROC_MEANS | 20 | PROC_MEANS_OUTPUT |
| PROC_FREQ | 15 | — |
| MACRO_BASIC | 25 | — |
| MACRO_CONDITIONAL | 20 | — |
| PROC_SORT | 15 | — |
| PROC_REG_LOGISTIC | 20 | — |
| PROC_IMPORT_EXPORT | 15 | — |
| MISSING_VALUE_HANDLING | 20 | MISSING_VALUE |

Categories with an associated failure mode receive 10 extra targeted pairs specifically designed to teach the LLM the correct pattern for that pitfall.

### KB Schema (16 Fields)

| Field | Type | Purpose |
|-------|------|---------|
| example_id | string (UUID) | Unique identifier |
| sas_code | string | SAS source snippet |
| python_code | string | Python translation |
| embedding | float32[768] | Nomic text embedding for vector search |
| partition_type | string | SAS construct type (DATA_STEP, PROC_SQL, etc.) |
| complexity_tier | string | LOW / MOD / HIGH |
| target_runtime | string | python / pyspark |
| verified | bool | Cross-verification passed |
| source | string | Origin (gold_standard, kb_gen, user_correction, etc.) |
| failure_mode | string | Associated failure mode (if any) |
| verification_method | string | How it was verified |
| verification_score | float32 | Cross-verification confidence |
| category | string | SAS category from the 15-category matrix |
| version | int32 | KB version number (for rollback) |
| superseded_by | string | Points to newer version if updated |
| created_at | string (ISO 8601) | Creation timestamp |

### Pydantic Output Models

Structured LLM responses via `instructor`:
- `GeneratedSAS`: Prompt A output (sas_code, category, complexity_tier, failure_mode, description)
- `ConvertedPython`: Prompt B output (python_code, target_runtime, imports_needed, notes)
- `CrossVerifyResult`: Prompt C output (equivalent, issues, confidence)

### KB Stats

- **Current**: 330 verified pairs across all 15 categories
- **Target**: 380 pairs (50 more targeting weak categories)
- **Gold standard**: 45 manually curated pairs (separate, used for benchmarking only)
- **Rollback**: Any KB mutation is logged in DuckDB; rollback script can revert to any prior version

---

## 29. Week-by-Week Build History

A chronological record of what was built each week, tracking the project from zero to its current state.

### Weeks 1–2: Foundation (L2-A)

**Deliverables**: Project scaffold, 3 entry agents (FileAnalysisAgent, CrossFileDependencyResolver, RegistryWriterAgent), DataLineageExtractor, SQLite persistence layer, 50-file gold standard corpus (721 blocks across 3 tiers).

**Key decisions**: BaseAgent ABC with single `async process()` method. Pydantic v2 for all data models. structlog for JSON logging. 9-value PartitionType enum.

**Tests**: ~20 | **Commit**: `b2b2dd4`

### Weeks 2–3: Streaming Parser (L2-B)

**Deliverables**: StreamAgent (line-by-line reader), StateAgent (FSM parser with 12 states), streaming pipeline wired via `asyncio.Queue` with backpressure (queue size 100). Producer/consumer pattern with graceful shutdown.

**Tests**: ~35

### Weeks 3–4: Boundary Detection (L2-C)

**Deliverables**: BoundaryDetector with dual strategy — deterministic rules first (lark grammar + regex, handles ~80% of boundaries), LLM fallback for ambiguous cases. PartitionBuilder constructs PartitionIR objects from detected boundaries.

**Tests**: ~60

### Week 4: Complexity Scoring (L2-D)

**Deliverables**: ComplexityAgent with ML-calibrated scoring (scikit-learn ensemble, ECE < 0.08). StrategyAgent maps (risk_level, partition_type, has_dependencies) → (RAG paradigm, LLM tier). 14 features extracted from SAS code (6 structural + 8 SAS-specific pattern indicators).

**Tests**: ~80

### Weeks 5–6: RAPTOR Clustering (L2-C)

**Deliverables**: NomicEmbedder (768-dim, CPU, with prefix handling for search vs. document embeddings), GMMClusterer (BIC convergence, τ=0.72 soft assignment threshold), ClusterSummarizer (3-tier LLM fallback: Azure → Groq → extractive), RAPTORTreeBuilder (recursive bottom-up tree, macro density-aware depth control).

**Tests**: ~100

### Week 7: Persistence + Indexing (L2-E)

**Deliverables**: PersistenceAgent (SQLite writer), IndexAgent (NetworkX directed graph, SCC detection via Tarjan's algorithm for identifying circular dependencies), DuckDB 7-table analytics schema.

**Tests**: 115 | **Commit**: `1fcba49`

### Week 8: Orchestrator

**Deliverables**: PartitionOrchestrator (LangGraph StateGraph, initially 9 nodes), RedisCheckpointManager (save every 50 blocks, find latest, clear), LLMAuditLogger (DuckDB write for every LLM call).

**Tests**: 126

### Week 9: Robustness + Knowledge Base

**Deliverables**: RateLimitSemaphore (Azure: 10 concurrent, Groq: 3), CircuitBreaker (3-state: CLOSED/OPEN/HALF_OPEN), MemoryMonitor (psutil RSS tracking), file-size strategy (standard/large/huge). KBWriter (LanceDB, IVF-64 cosine index), kb_changelog (DuckDB), generate_kb_pairs.py (dual-LLM chain: Azure generates, Groq verifies), kb_rollback.py. KB reached 330 pairs across 15 categories with 6 targeted failure modes.

**Architecture change**: Azure OpenAI promoted to primary LLM (was Groq). Old chain: Ollama 8B → Groq 70B. New chain: Azure GPT-4o → Groq (fallback + cross-verifier).

**Tests**: 144 | **Commit**: `be15d49`

### Week 10: Translation (L3)

**Deliverables**: TranslationAgent (3-tier RAG routing: Static/GraphRAG/Agentic), ValidationAgent (subprocess sandbox with removed builtins, multiprocessing.Process + .kill()), TranslationPipeline (orchestrates translation → validation → retry → cross-verify). Full LLM fallback chain: Azure → Groq → PARTIAL. Cross-verification on independent provider. Reflexion retry loop (up to 2 retries with error context).

**Tests**: 169 | **Commit**: `b542c25`

### Week 11: Merge + Continuous Learning (L4)

**Deliverables**: ImportConsolidator (deduplicates and orders imports), DependencyInjector (injects shared variables across partitions), ScriptMerger (merges translated partitions into final script), ReportAgent (HTML report generation with accuracy metrics). FeedbackIngestionAgent (processes user corrections into KB format), ConversionQualityMonitor (tracks quality trends), RetrainTrigger (initiates model retraining when quality drops).

KB expanded from 200 → 330 pairs.

**Tests**: 191 | **Commit**: `2c5a6da`

### Week 12: Evaluation Infrastructure

**Deliverables**: Ablation study infrastructure — flat_index.py (baseline retrieval), query_generator.py (generates test queries from gold corpus), ablation_runner.py (runs pipeline with/without RAPTOR), init_ablation_db.py (DuckDB schema), analyze_ablation.py (generates plots and statistics).

**Tests**: 198 | **Commit**: `dbaebf1`

### Week 13: Restructure + Enterprise (v3.0.0)

**Deliverables**: Orchestrator reduced from 11 nodes to 8 via facade pattern (each node-agent wraps 1–4 sub-agents). 44 audit fixes (grade B+ → A-) + 20 post-audit fixes. Azure Monitor OpenTelemetry integration. GitHub Actions CI/CD (6 jobs: lint → test → security → docker build → deploy → benchmark). CodeQL security scanning. Docker multi-stage build + 3-service compose. Dependabot monthly checks.

**Key fixes**: ValidationAgent sandbox changed from `threading.Thread` (leaky) to `multiprocessing.Process` + `.kill()` (true isolation). config_manager.py rewritten — source YAML now read-only, runtime state in separate file. Dockerfile COPY path corrected for renamed package.

**Tests**: 221

### Week 14: Buffer + Polish

Defense preparation, documentation, remaining deliverables.

### Week 15+: Research Extensions (v3.1.0)

**Deliverables**: Z3 formal verification agent (11 SMT patterns, 41% provability on LOW-risk blocks), HyperRAPTOR (Poincaré ball clustering, +6% hit-rate@5, +9.5% MRR), QLoRA fine-tuned Qwen2.5-Coder-7B (1,200 pairs, perplexity 2.61, DPO with 87 correction pairs, GGUF Q4_K_M ~4.5GB), CDAIS + MIS formal adversarial testing framework.

**Architecture change**: Ollama `minimax-m2.7:cloud` promoted to primary (10/10 on torture test). New 5-tier chain: Local GGUF → Ollama → Azure → Groq → PARTIAL.

**Ablation best config**: fine-tuned 7B + HyperRAPTOR + Z3 = 87.4% translation accuracy.

**Tests**: 248+ (309 collected including planning branch)

---

## 30. File-by-File Reference

### Configuration Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Python project config: name, version, pytest settings, tool configs |
| `backend/config/settings.py` | Pydantic Settings model: loads all env vars with defaults |
| `backend/config/constants.py` | Global constants (max file size, supported extensions, etc.) |
| `backend/config/project_config.yaml` | Runtime pipeline configuration (adjustable without code changes) |

### Prompt Templates (`backend/partition/prompts/`)

| Template | Used by | Purpose |
|----------|---------|---------|
| `translation_static.j2` | Static RAG | Simple translation prompt with KB examples |
| `translation_graph.j2` | GraphRAG | Translation prompt with dependency context |
| `translation_agentic.j2` | Agentic RAG | Complex translation prompt with reflection + error context |
| `cross_verify.j2` | TranslationAgent | Independent verification prompt (Prompt C) |
| `reflection.j2` | TranslationAgent | Self-reflection prompt for retry |
| `entity_extraction.j2` | RAPTOR | Entity extraction from SAS code for clustering |

### `backend/partition/prompts/manager.py` — PromptManager
Loads Jinja2 templates and renders them with partition-specific variables (source code, risk level, KB examples, error context, etc.).

### Test Files (`backend/tests/`)

| Test File | What it tests |
|-----------|--------------|
| `test_streaming.py` | StreamAgent, StateAgent FSM, pipeline performance |
| `test_boundary_detector.py` | BoundaryDetector + LLM resolver accuracy |
| `test_complexity_agent.py` | ComplexityAgent ML scoring + rule fallback |
| `test_strategy_agent.py` | StrategyAgent routing logic |
| `test_rag.py` | RAGRouter, all 3 paradigms |
| `test_raptor.py` | RAPTOR tree building |
| `test_translation.py` | TranslationAgent, cross-verify, reflexion |
| `test_orchestration.py` | Full pipeline integration |
| `test_persistence.py` | SQLite persistence |
| `test_evaluation.py` | Flat index + ablation queries |
| `test_merge_retraining.py` | MergeAgent + KB feedback loop |
| `test_file_analysis.py` | FileAnalysisAgent |
| `test_cross_file_deps.py` | CrossFileDepsResolver |
| `test_data_lineage.py` | DataLineageExtractor |
| `test_registry_writer.py` | RegistryWriterAgent |
| `test_robustness_kb.py` | KB rollback/versioning |
| `test_integration.py` | End-to-end API tests |
| `test_z3_verification.py` | Z3 formal verification patterns |
| `test_z3_effect.py` | Z3 effect on translation quality |
| `test_cdais.py` | CDAIS adversarial testing |
| `test_critical_paths.py` | Critical path coverage |
| `test_local_model_client.py` | Local GGUF model loading |
| `test_regression.py` | Regression detection |
| `regression/test_ablation.py` | RAPTOR vs flat index ablation |
| `conftest.py` | Shared pytest fixtures |

### Test Fixtures (`backend/tests/fixtures/`)

| File | Purpose |
|------|---------|
| `torture_test.sas` | 10 hard SAS patterns: RETAIN, FIRST./LAST., correlated SQL, macros, hash, PROC MEANS, TRANSPOSE |
| `chart_dashboard.sas` | SAS ODS Graphics dashboard code |
| `chart_scatter_reg.sas` | PROC SGPLOT scatter with regression |
| `chart_vbar.sas` | PROC SGPLOT vertical bar chart |

### Operational Scripts (`backend/scripts/ops/`)

| Script | Purpose |
|--------|---------|
| `run_pipeline.py` | CLI entry point: run the pipeline on a SAS file |
| `submit_correction.py` | Submit a correction to the KB from CLI |
| `verify_deliverables.py` | Check that all required deliverables exist |
| `view_db.py` | Inspect database contents |

### Example Files (`backend/examples/`)

| File | Purpose |
|------|---------|
| `demo_pipeline.py` | Demonstrates the pipeline API programmatically |
| `run_week1_demo.py` | Week 1 milestone demo script |

---

## Summary of Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **LangGraph over LangChain** | Explicit state machines, deterministic execution, per-node checkpointing |
| **3 LLM providers** | Resilience (fallback chain) + accuracy (cross-verification on different provider) |
| **4 databases** | Each optimized for its access pattern: ACID (SQLite), crash recovery (Redis), vector search (LanceDB), analytics (DuckDB) |
| **Z3 formal verification** | Mathematical proof of correctness, not just testing |
| **CDAIS adversarial testing** | Synthesizes edge cases that would be missed by normal testing |
| **RAPTOR clustering** | Hierarchical retrieval outperforms flat search on complex partitions |
| **3 RAG paradigms** | Right-sized retrieval: simple blocks don't need graph traversal |
| **Subprocess sandbox** | True process isolation prevents translated code from escaping |
| **Azure Key Vault + OIDC** | Zero stored credentials in code, CI, or env vars |
| **Docker multi-stage build** | Separates build tools from runtime for smaller images |
| **Facade pattern (8 nodes)** | Orchestrator sees 8 clean nodes; complexity is internal to each facade |
