# Codara — Complete Project Explanation (Deep Dive)

> **Codara** is a SAS-to-Python conversion accelerator. It takes legacy SAS statistical programs, parses them, understands their structure, and translates them into equivalent Python code using AI — then formally verifies the result is correct. This document explains every mechanism, every file, every design decision, with detailed schemas, flow diagrams, and internal implementation specifics.

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [Problem Statement & Motivation](#2-problem-statement--motivation)
3. [Research Foundation — RAPTOR (ICLR 2024)](#3-research-foundation--raptor-iclr-2024)
4. [End-to-End Request Flow (Detailed)](#4-end-to-end-request-flow-detailed)
5. [Backend API Layer](#5-backend-api-layer)
6. [The 8-Node Pipeline (LangGraph)](#6-the-8-node-pipeline-langgraph)
7. [Node 1: File Processing (L2-A)](#7-node-1-file-processing-l2-a)
8. [Node 2: Streaming Parser (L2-B)](#8-node-2-streaming-parser-l2-b)
9. [Node 3: Chunking / Boundary Detection (L2-C)](#9-node-3-chunking--boundary-detection-l2-c)
10. [Node 4: RAPTOR Semantic Clustering (L2-C)](#10-node-4-raptor-semantic-clustering-l2-c)
11. [Node 5: Risk Routing / Complexity Scoring (L2-D)](#11-node-5-risk-routing--complexity-scoring-l2-d)
12. [Node 6: Persistence + Indexing (L2-E)](#12-node-6-persistence--indexing-l2-e)
13. [Node 7: Translation (L3) — The Core](#13-node-7-translation-l3--the-core)
14. [Node 8: Merge (L4)](#14-node-8-merge-l4)
15. [The Three RAG Paradigms](#15-the-three-rag-paradigms)
16. [LLM Provider Chain & Fallback Mechanism](#16-llm-provider-chain--fallback-mechanism)
17. [Verification Layer](#17-verification-layer)
18. [The Four Databases](#18-the-four-databases)
19. [Knowledge Base System](#19-knowledge-base-system)
20. [Resilience Mechanisms](#20-resilience-mechanisms)
21. [Authentication & Security](#21-authentication--security)
22. [Frontend](#22-frontend)
23. [CI/CD Pipeline](#23-cicd-pipeline)
24. [Docker & Azure Infrastructure](#24-docker--azure-infrastructure)
25. [Evaluation & Benchmarking](#25-evaluation--benchmarking)
26. [Gold Standard Corpus (50 Files, 721 Blocks)](#26-gold-standard-corpus-50-files-721-blocks)
27. [CDAIS — Formal Adversarial Testing (Deep Dive)](#27-cdais--formal-adversarial-testing-deep-dive)
28. [MIS — Migration Invariant Synthesis](#28-mis--migration-invariant-synthesis)
29. [HyperRAPTOR — Poincare Ball Clustering](#29-hyperraptor--poincare-ball-clustering)
30. [QLoRA Fine-Tuning Pipeline](#30-qlora-fine-tuning-pipeline)
31. [The 6 Failure Modes (Detailed)](#31-the-6-failure-modes-detailed)
32. [KB Dual-LLM Generation Chain](#32-kb-dual-llm-generation-chain)
33. [Azure Enterprise Architecture Rationale](#33-azure-enterprise-architecture-rationale)
34. [Code Quality & Audit Trail](#34-code-quality--audit-trail)
35. [Version History (CHANGELOG)](#35-version-history-changelog)
36. [Week-by-Week Build History](#36-week-by-week-build-history)
37. [File-by-File Reference](#37-file-by-file-reference)

---

## 1. High-Level Architecture

Codara is a **three-tier stack**: a React frontend, a FastAPI backend, and a LangGraph pipeline engine with formal verification.

### System Architecture Schema

```
 ┌───────────────────────────────────────────────────────────────────────┐
 │                        USER'S BROWSER                                │
 │  React 18 + TypeScript + Vite + Tailwind + shadcn/ui + Zustand      │
 │  Port 5173 (dev) / 8080 (Docker/nginx)                              │
 └───────────────────────┬──────────────────────────────────────────────┘
                         │  HTTP /api/* (proxy)
                         ▼
 ┌───────────────────────────────────────────────────────────────────────┐
 │                     FASTAPI BACKEND (port 8000)                      │
 │                                                                      │
 │  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌───────┐  ┌──────────┐  │
 │  │  Auth   │  │Conversions│  │   KB     │  │ Admin │  │Analytics │  │
 │  │ Routes  │  │  Routes   │  │ Routes   │  │Routes │  │ Routes   │  │
 │  └────┬────┘  └─────┬─────┘  └────┬─────┘  └───┬───┘  └────┬─────┘  │
 │       │             │             │             │            │        │
 │       ▼             ▼             ▼             ▼            ▼        │
 │  ┌───────────────────────────────────────────────────────────────┐    │
 │  │              Service Layer (pipeline_service.py)              │    │
 │  │        blob_service / conversion_service / queue_service      │    │
 │  └──────────────────────────┬────────────────────────────────────┘    │
 └─────────────────────────────┼────────────────────────────────────────┘
                               │  BackgroundTasks / Azure Queue
                               ▼
 ┌───────────────────────────────────────────────────────────────────────┐
 │              LANGGRAPH PIPELINE ENGINE (8 nodes)                     │
 │                                                                      │
 │  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐         │
 │  │  Node 1  │──▶│  Node 2  │──▶│  Node 3  │──▶│  Node 4  │         │
 │  │FileProc  │   │Streaming │   │ Chunking │   │  RAPTOR  │         │
 │  │ (L2-A)   │   │ (L2-B)   │   │ (L2-C)   │   │ (L2-C)   │         │
 │  └──────────┘   └──────────┘   └──────────┘   └──────────┘         │
 │       │                                             │                │
 │  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐         │
 │  │  Node 5  │──▶│  Node 6  │──▶│  Node 7  │──▶│  Node 8  │──▶ END  │
 │  │RiskRoute │   │ Persist  │   │Translate │   │  Merge   │         │
 │  │ (L2-D)   │   │ (L2-E)   │   │  (L3)    │   │  (L4)    │         │
 │  └──────────┘   └──────────┘   └──────────┘   └──────────┘         │
 │                                      │                               │
 │                      ┌───────────────┼───────────────┐               │
 │                      ▼               ▼               ▼               │
 │               ┌────────────┐  ┌────────────┐  ┌────────────┐        │
 │               │ 6 LLM      │  │ 4 Databases│  │Verification│        │
 │               │ Providers   │  │            │  │   Layer    │        │
 │               └────────────┘  └────────────┘  └────────────┘        │
 └───────────────────────────────────────────────────────────────────────┘

 LLM Providers:                 Databases:              Verification:
 ┌──────────────────┐          ┌──────────────┐        ┌──────────────┐
 │ Tier 0: Local    │          │ SQLite       │        │ Z3 SMT (11   │
 │   GGUF (Qwen)    │          │  (ACID ops)  │        │  patterns)   │
 │ Tier 1: Ollama   │          │ Redis        │        │ CDAIS (6     │
 │   (minimax)      │          │  (checkpoint)│        │  error cls)  │
 │ Tier 2: Azure    │          │ LanceDB      │        │ MIS (12      │
 │   (GPT-4o)       │          │  (vectors)   │        │  invariants) │
 │ Tier 3: Groq     │          │ DuckDB       │        │ Sandbox      │
 │   (LLaMA-70B)    │          │  (analytics) │        │  (exec)      │
 │ Tier 4: Gemini   │          └──────────────┘        │ Cross-verify │
 │ Tier 5: Cerebras │                                  │  (multi-LLM) │
 └──────────────────┘                                  └──────────────┘
```

### Technology Stack Table

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| **Frontend** | React | 18 | UI framework |
| | TypeScript | 5.x | Type safety |
| | Vite | 5.x | Bundler + dev server |
| | Tailwind CSS | 3.x | Utility-first CSS |
| | shadcn/ui | — | 57 UI components |
| | Zustand | 4.x | State management |
| | React Router | v6 | Client routing |
| | framer-motion | — | Animations |
| | bun | 1.x | Package manager |
| **Backend** | FastAPI | 0.100+ | REST API framework |
| | Python | 3.11 | Language runtime |
| | SQLAlchemy | 2.x | ORM |
| | Pydantic | v2 | Schema validation |
| | structlog | — | JSON logging |
| | uvicorn | — | ASGI server |
| **Pipeline** | LangGraph | — | StateGraph engine |
| | instructor | — | Structured LLM output |
| | sentence-transformers | — | Nomic embeddings |
| | scikit-learn | — | GMM clustering + LogReg |
| | NetworkX | — | Dependency graphs |
| | z3-solver | — | Formal verification |
| | PyTorch | — | Embedding inference |
| **Infra** | Docker | — | Containerization |
| | GitHub Actions | — | CI/CD (6 jobs) |
| | Azure Container Apps | — | Serverless hosting |
| | Azure Key Vault | — | Secrets management |
| | Redis | 7 | Crash-recovery checkpoints |

---

## 2. Problem Statement & Motivation

### Why This Project Exists

Enterprises running legacy SAS codebases face a critical convergence of pressures:

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                   THE SAS MIGRATION PROBLEM                              │
 │                                                                          │
 │  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐    │
 │  │   HIGH COST      │     │  TALENT CRISIS   │     │  REGULATORY     │    │
 │  │                  │     │                  │     │  PRESSURE       │    │
 │  │ SAS licenses:    │     │ Fewer new devs   │     │ Compliance      │    │
 │  │ $5K-$50K/seat/yr │     │ learn SAS.       │     │ mandates open-  │    │
 │  │ per module       │     │ Average SAS dev   │     │ source stacks   │    │
 │  │                  │     │ age: 45+          │     │ for auditability│    │
 │  └────────┬────────┘     └────────┬────────┘     └────────┬────────┘    │
 │           │                       │                       │              │
 │           └───────────────────────┼───────────────────────┘              │
 │                                   ▼                                      │
 │                    ┌─────────────────────────────┐                        │
 │                    │   MANUAL CONVERSION IS       │                        │
 │                    │   SLOW AND ERROR-PRONE       │                        │
 │                    │                              │                        │
 │                    │   10K lines → 6-12 months    │                        │
 │                    │   1 dev, no verification     │                        │
 │                    │   Silent semantic errors     │                        │
 │                    └──────────────┬──────────────┘                        │
 │                                   ▼                                      │
 │                    ┌─────────────────────────────┐                        │
 │                    │   CODARA AUTOMATES THIS      │                        │
 │                    │                              │                        │
 │                    │   10K lines → minutes         │                        │
 │                    │   AI + formal verification    │                        │
 │                    │   Provable correctness (Z3)   │                        │
 │                    └─────────────────────────────┘                        │
 └──────────────────────────────────────────────────────────────────────────┘
```

### The 6 Identified Failure Modes in SAS→Python Translation

These are the specific patterns where naive or even careful manual translation silently produces wrong results. Codara was designed around detecting and preventing all 6:

| # | Failure Mode | SAS Construct | Why It's Hard | How Codara Handles It |
|---|-------------|---------------|---------------|----------------------|
| 1 | **DATE_ARITHMETIC** | SAS dates = days since 1960-01-01 | Different epoch than Python (1970) | KB examples + Z3 arithmetic proof |
| 2 | **MERGE_LOGIC** | `MERGE` with `BY` + `IN=` flags | Complex join semantics, FIRST./LAST. | Dedicated KB category + graph RAG |
| 3 | **RETAIN_STATE** | `RETAIN` + row-by-row processing | Stateful iteration ≠ pandas vectorization | CDAIS adversarial testing |
| 4 | **MACRO_EXPANSION** | `%MACRO`, `%LET`, nested `%DO` | Text substitution engine, no Python equivalent | Deep RAPTOR tree + agentic RAG |
| 5 | **PROC_SQL_DIALECT** | PROC SQL with SAS-specific functions | SAS SQL extensions not in standard SQL | Failure mode detection + KB lookup |
| 6 | **FORMAT_INFORMATS** | `FORMAT`, `INFORMAT`, `PUT()`, `INPUT()` | 100+ proprietary format codes | KB coverage matrix (330 pairs) |

### The Core Insight

```
 BEFORE Codara (naive pipeline):
 ┌───────────┐     ┌──────────┐     ┌──────────┐
 │ SAS code  │────▶│ LLM      │────▶│ Python   │    No proof it's correct.
 │           │     │ (GPT-4o) │     │ code     │    ValidationAgent only checks
 └───────────┘     └──────────┘     └──────────┘    it doesn't CRASH, not that
                                                     it computes CORRECTLY.

 AFTER Codara (full pipeline):
 ┌───────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
 │ SAS code  │────▶│ RAG +    │────▶│ Python   │────▶│ Sandbox  │────▶│ Z3 SMT   │
 │           │     │ LLM      │     │ code     │     │ exec()   │     │ Proof    │
 └───────────┘     │ (6 provs)│     └──────────┘     │ (15s     │     │          │
                   │ + KB 330 │                      │ timeout) │     │ PROVED?  │
                   │ + RAPTOR │                      └──────────┘     │ or CTREX │
                   └──────────┘                                       └──────────┘
                                                                          │
                                                              ┌───────────┴──────────┐
                                                              │                      │
                                                        PROVED (41%)          COUNTEREXAMPLE
                                                        → merge               → re-translate
                                                                               with ctrex in
                                                                               prompt (CEGAR)
```

---

## 3. Research Foundation — RAPTOR (ICLR 2024)

### Paper Reference

| | |
|---|---|
| **Paper** | *RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval* |
| **Venue** | ICLR 2024 — arXiv:2401.18059 |
| **Authors** | Sarthi, Abdullah, Goldie, Liskovich, Sherstinsky, Potts & Manning (Stanford NLP) |

### Original Contribution

RAPTOR builds **hierarchical tree summaries** of long documents using:
- **Gaussian Mixture Model (GMM)** clustering with BIC minimization for automatic k-selection
- **Recursive LLM summarization** of clusters at multiple abstraction levels
- Retrieval at **leaf** (fine-grained), **cluster** (thematic), and **root** (document intent) levels

### Our Adaptation to SAS Partitioning

Instead of treating every `DATA` step or `PROC` block as a flat, independent chunk, we cluster semantically related SAS blocks into a **recursive tree**:

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │  RAPTOR Adaptation: Natural Language Documents → SAS Code Blocks     │
 │                                                                      │
 │  PAPER (Original):                    CODARA (Adaptation):           │
 │  ┌──────────────────┐                 ┌──────────────────┐          │
 │  │ Text paragraphs   │                 │ PartitionIR       │          │
 │  │ as leaf nodes      │                 │ (9 canonical types)│          │
 │  │                    │                 │ as leaf nodes      │          │
 │  └────────┬───────────┘                 └────────┬───────────┘          │
 │           │                                      │                    │
 │  ┌────────▼───────────┐                 ┌────────▼───────────┐          │
 │  │ GMM on text embeds  │                 │ GMM on code embeds  │          │
 │  │ (OpenAI ada-002)    │                 │ (Nomic v1.5, 768d)  │          │
 │  └────────┬───────────┘                 └────────┬───────────┘          │
 │           │                                      │                    │
 │  ┌────────▼───────────┐                 ┌────────▼───────────┐          │
 │  │ OpenAI summaries    │                 │ Groq LLaMA-70B sums │          │
 │  │ of each cluster     │                 │ with hash caching    │          │
 │  └────────┬───────────┘                 └────────┬───────────┘          │
 │           │                                      │                    │
 │  ┌────────▼───────────┐                 ┌────────▼───────────┐          │
 │  │ Fixed max_depth=4   │                 │ Dynamic depth:       │          │
 │  │                    │                 │ macro_density > 0.4  │          │
 │  │                    │                 │ → depth=5, else 3    │          │
 │  └────────────────────┘                 └────────────────────┘          │
 │                                                                      │
 │  KEY DOMAIN-SPECIFIC CHANGES:                                         │
 │  1. Leaf content = SAS code blocks (not text paragraphs)              │
 │  2. BIC convergence trigger: ΔBIc < 0.01 stops recursion             │
 │  3. macro_density > 0.4 → deeper trees (enterprise SAS files)        │
 │  4. Retrieval level maps to RAG paradigm:                             │
 │     ┌────────────┬─────────────┬────────────────────┐                │
 │     │ Level      │ RAG Type    │ Use Case            │                │
 │     ├────────────┼─────────────┼────────────────────┤                │
 │     │ Leaf       │ Static RAG  │ Simple block lookup  │                │
 │     │ Cluster    │ GraphRAG    │ Macro families       │                │
 │     │ Root       │ Agentic RAG │ File-level planning  │                │
 │     └────────────┴─────────────┴────────────────────┘                │
 └──────────────────────────────────────────────────────────────────────┘
```

### Why GMM Over K-Means?

GMM (Gaussian Mixture Model) assigns **soft cluster membership** — a partition can partially belong to multiple clusters. This is critical for SAS code where a macro call may logically belong to both an "ETL" cluster and a "data quality" cluster. K-Means forces hard assignment; GMM produces overlapping clusters that reflect real SAS structure.

### Target vs Achieved Metrics

| Metric | Target | Achieved | Status |
|--------|--------|----------|--------|
| Boundary accuracy | > 90% | 79.3% (572/721) | In progress |
| RAPTOR hit-rate @5 | > 82% | 96.38% | Exceeded |
| ECE (calibration) | < 0.08 | 0.06 | Exceeded |
| Real agents (strict SRP) | ≤ 10 | 8 | Exceeded |
| KB pairs | 330 | 330+ | Met |
| Canonical partition types | 9 | 10 (+ UNCLASSIFIED) | Met |

---

## 4. End-to-End Request Flow (Detailed)

This section traces a single `.sas` file upload through the entire system, step by step.

### Phase 1: Upload (Frontend → API)

```
 User drags .sas file ──▶ Workspace.tsx Dropzone
                              │
                              ▼
                     conversion-store.ts
                     upload() action
                              │
                              ▼
                     POST /api/conversions/upload
                     (multipart/form-data)
                              │
                              ▼
                     conversions.py:upload_files()
                       ├── Validate extension (.sas only)
                       ├── Validate MIME type
                       ├── Validate size (<50MB)
                       ├── Generate file_id = "file-{uuid8}"
                       ├── blob_service.upload(file_id, name, bytes)
                       │     └── saves to backend/uploads/{file_id}/
                       └── Return SasFileOut JSON
```

### Phase 2: Start Conversion (API → Pipeline)

```
 User clicks "Start Conversion"
         │
         ▼
 POST /api/conversions/start
 Body: { fileIds: ["file-abc12345"] }
         │
         ▼
 conversions.py:start_conversion()
   ├── Create ConversionRow (status="queued")
   ├── Create 8 ConversionStageRow records (all "pending")
   ├── session.commit()
   │
   ├── Try: queue_service.enqueue_job()  (Azure Queue - production)
   │     └── If unavailable:
   │         BackgroundTasks.add_task(_guarded_pipeline)
   │           └── asyncio.Semaphore(5) limits concurrent pipelines
   │               └── asyncio.to_thread(run_pipeline_sync, ...)
   │
   └── Return ConversionOut JSON immediately (non-blocking)
```

### Phase 3: Pipeline Execution (8 Nodes)

```
 run_pipeline_sync(conv_id, file_id, filename, db_path)
   │
   ├── Update ConversionRow → status="running"
   ├── Instantiate PartitionOrchestrator(redis_url, duckdb_path)
   │     ├── RedisCheckpointManager(redis_url)
   │     ├── LLMAuditLogger(duckdb_path)
   │     ├── MemoryMonitor + configure_memory_guards()
   │     └── self.graph = _build_graph()  ← LangGraph StateGraph compiled
   │
   ├── orchestrator.run([sas_file_path])
   │     │
   │     ├── Generate run_id, trace_id (UUID4)
   │     ├── Build initial PipelineState (27 fields, all defaults)
   │     ├── Check Redis for existing checkpoints
   │     │
   │     └── await self.graph.ainvoke(initial_state)
   │           │
   │           ├── Node 1: file_process   ← FATAL on failure
   │           ├── Node 2: streaming      ← checkpoint every 50 blocks
   │           ├── Node 3: chunking       ← boundary detection
   │           ├── Node 4: raptor         ← semantic clustering
   │           ├── Node 5: risk_routing   ← complexity scoring
   │           ├── Node 6: persist_index  ← SQLite + NetworkX
   │           ├── Node 7: translation    ← LLM + validate + verify
   │           └── Node 8: merge          ← final script + report
   │
   ├── Update each ConversionStageRow as nodes complete
   ├── Write python_code + report to ConversionRow
   └── Update ConversionRow → status="completed"
```

### Phase 4: Polling + Display (Frontend)

```
 conversion-store.ts: startPolling()
   │
   └── setInterval(1200ms):  ← every 1.2 seconds
         GET /api/conversions/{conv_id}
           │
           ├── Returns: status, stages[], python_code, report
           │
           └── Frontend updates:
                 ├── Progress bar (8 stages with status badges)
                 ├── Side-by-side diff view (SAS vs Python)
                 └── Download button (when completed)
```

### Phase 5: Download

```
 GET /api/conversions/{id}/download
   │
   └── Creates ZIP in-memory:
         ├── {filename}_converted.py    (translated Python)
         └── {filename}_report.html     (HTML conversion report)
```

---

## 5. Backend API Layer

### Application Initialization Flow

```
 backend/api/main.py → app = FastAPI()
   │
   ├── @app.on_event("startup")
   │     ├── init_api_db(engine)        ← create all 8 SQLite tables
   │     └── seed_default_users()       ← admin + user accounts
   │           ├── admin: CODARA_ADMIN_PASSWORD or random
   │           └── user:  CODARA_USER_PASSWORD or random
   │           └── Passwords printed to stdout on first boot
   │
   ├── CORS middleware
   │     └── origins: localhost:5173, :8080, :8000, FRONTEND_URL
   │
   ├── Include route modules:
   │     ├── /api/auth/*           (auth.py)
   │     ├── /api/conversions/*    (conversions.py)
   │     ├── /api/knowledge-base/* (knowledge_base.py)
   │     ├── /api/admin/*          (admin.py)
   │     ├── /api/analytics/*      (analytics.py)
   │     ├── /api/notifications/*  (notifications.py)
   │     └── /api/settings/*       (settings.py)
   │
   ├── Error handler middleware   (error_handler.py)
   └── Logging middleware         (logging_middleware.py)
```

### SQLite Database Schema (8 Tables)

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │                        codara_api.db (WAL mode)                       │
 ├────────────────────────────────────────────────────────────────────────┤
 │                                                                        │
 │  ┌──────────────┐          ┌──────────────────┐                        │
 │  │   users       │          │   conversions     │                        │
 │  ├──────────────┤     1:N  ├──────────────────┤                        │
 │  │ id (PK)      │◄────────│ user_id (FK)     │                        │
 │  │ email (UQ)   │          │ id (PK)          │                        │
 │  │ name         │          │ file_name        │                        │
 │  │ hashed_pwd   │          │ status           │                        │
 │  │ role         │          │ runtime          │                        │
 │  │ status       │          │ duration         │                        │
 │  │ conv_count   │          │ accuracy         │                        │
 │  │ default_rt   │          │ sas_code (TEXT)   │                        │
 │  │ email_notif  │          │ python_code (TEXT) │                        │
 │  │ email_verif  │          │ validation_report │                        │
 │  │ verif_token  │          │ merge_report      │                        │
 │  │ github_id(UQ)│          │ created_at        │                        │
 │  │ created_at   │          │ updated_at        │                        │
 │  └──────────────┘          └───────┬──────────┘                        │
 │                                     │ 1:N                               │
 │                            ┌────────┴──────────┐                        │
 │                            │conversion_stages  │                        │
 │                            ├───────────────────┤                        │
 │                            │ id (PK, auto)     │                        │
 │                            │ conversion_id (FK)│                        │
 │                            │ stage             │                        │
 │                            │ status            │                        │
 │                            │ latency           │                        │
 │                            │ retry_count       │                        │
 │                            │ warnings (JSON)   │                        │
 │                            │ description       │                        │
 │                            │ started_at        │                        │
 │                            │ completed_at      │                        │
 │                            └───────────────────┘                        │
 │                                                                        │
 │  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐           │
 │  │  kb_entries   │     │ kb_changelog  │     │  audit_logs  │           │
 │  ├──────────────┤     ├──────────────┤     ├──────────────┤           │
 │  │ id (PK)      │◄───│ entry_id (FK)│     │ id (PK)      │           │
 │  │ sas_snippet  │     │ id (PK)      │     │ model        │           │
 │  │ python_trans │     │ action       │     │ latency      │           │
 │  │ category     │     │ user         │     │ cost         │           │
 │  │ confidence   │     │ timestamp    │     │ prompt_hash  │           │
 │  │ created_at   │     │ description  │     │ success      │           │
 │  │ updated_at   │     └──────────────┘     │ timestamp    │           │
 │  └──────────────┘                          └──────────────┘           │
 │                                                                        │
 │  ┌──────────────┐     ┌──────────────┐                                │
 │  │ corrections   │     │notifications │                                │
 │  ├──────────────┤     ├──────────────┤                                │
 │  │ id (PK)      │     │ id (PK)      │                                │
 │  │ conversion_id│     │ user_id (FK) │                                │
 │  │ corrected_cd │     │ title        │                                │
 │  │ explanation  │     │ message      │                                │
 │  │ category     │     │ type         │                                │
 │  │ submitted_at │     │ read (bool)  │                                │
 │  └──────────────┘     │ created_at   │                                │
 │                        └──────────────┘                                │
 └────────────────────────────────────────────────────────────────────────┘
```

### Complete API Endpoint Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/auth/login` | No | Email + password login, returns JWT |
| `POST` | `/api/auth/signup` | No | Create account with verification token |
| `POST` | `/api/auth/verify-email` | No | Validate verification token |
| `GET` | `/api/auth/github/url` | No | GitHub OAuth authorization URL |
| `POST` | `/api/auth/github/callback` | No | GitHub OAuth code exchange → JWT |
| `GET` | `/api/auth/me` | JWT | Current user profile |
| `POST` | `/api/auth/logout` | JWT | Stateless logout |
| `POST` | `/api/conversions/upload` | JWT | Upload .sas files (multipart) |
| `POST` | `/api/conversions/start` | JWT | Start pipeline (background task) |
| `GET` | `/api/conversions` | JWT | List user's conversions |
| `GET` | `/api/conversions/{id}` | JWT | Get conversion + stages |
| `GET` | `/api/conversions/{id}/download` | JWT | Download ZIP (Python + report) |
| `GET` | `/api/conversions/{id}/stream` | JWT | SSE real-time progress |
| `POST` | `/api/conversions/{id}/corrections` | JWT | Submit human correction |
| `GET` | `/api/knowledge-base` | JWT | List KB entries |
| `POST` | `/api/knowledge-base` | JWT | Create KB entry |
| `PUT` | `/api/knowledge-base/{id}` | JWT | Update KB entry |
| `DELETE` | `/api/knowledge-base/{id}` | JWT | Delete KB entry |
| `GET` | `/api/admin/users` | Admin | List all users |
| `PUT` | `/api/admin/users/{id}` | Admin | Update user role/status |
| `GET` | `/api/admin/audit-logs` | Admin | LLM call audit trail |
| `GET` | `/api/admin/system-health` | Admin | DB sizes, Redis, LLM status |
| `GET` | `/api/analytics` | JWT | Conversion stats + time-series |
| `GET` | `/api/notifications` | JWT | List unread notifications |
| `PUT` | `/api/notifications/{id}/read` | JWT | Mark notification as read |
| `GET` | `/api/health` | No | Health check: `{"status":"ok"}` |

### Rate Limiting Implementation

```
 In-memory sliding window per (IP, endpoint):
 ┌─────────────────────────────────────────────┐
 │  IP: 192.168.1.5  Endpoint: /auth/login     │
 │  Window: 60 seconds  Max: 5 attempts        │
 │                                              │
 │  Timestamps: [t-55s, t-40s, t-30s, t-10s]   │
 │  Count: 4/5 → ALLOWED                       │
 │                                              │
 │  Next attempt at t:                          │
 │  Count: 5/5 → BLOCKED (429 Too Many Reqs)   │
 └─────────────────────────────────────────────┘
```

---

## 6. The 8-Node Pipeline (LangGraph)

### `backend/partition/orchestration/orchestrator.py` — The Orchestrator

The `PartitionOrchestrator` is the heart of Codara. It builds a LangGraph `StateGraph` — a directed acyclic graph where each node is an async Python function that receives the full pipeline state and returns a partial update.

#### How the Graph is Built Internally

```python
# Inside _build_graph() — simplified
workflow = StateGraph(PipelineState)

workflow.add_node("file_process",   self._node_file_process)
workflow.add_node("streaming",      self._node_streaming)
workflow.add_node("chunking",       self._node_chunking)
workflow.add_node("raptor",         self._node_raptor)
workflow.add_node("risk_routing",   self._node_risk_routing)
workflow.add_node("persist_index",  self._node_persist_index)
workflow.add_node("translation",    self._node_translation)
workflow.add_node("merge",          self._node_merge)

workflow.set_entry_point("file_process")
workflow.add_edge("file_process",  "streaming")
workflow.add_edge("streaming",     "chunking")
workflow.add_edge("chunking",      "raptor")
workflow.add_edge("raptor",        "risk_routing")
workflow.add_edge("risk_routing",  "persist_index")
workflow.add_edge("persist_index", "translation")
workflow.add_edge("translation",   "merge")
workflow.add_edge("merge",         END)

self.graph = workflow.compile()
```

#### Graph Execution Schema

```
 ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
 │  file_process │────▶│  streaming   │────▶│   chunking   │────▶│    raptor     │
 │   (L2-A)      │     │   (L2-B)     │     │   (L2-C)     │     │   (L2-C)     │
 │               │     │              │     │              │     │              │
 │ FileProcessor │     │ StreamAgent  │     │ ChunkingAgent│     │ RAPTORAgent  │
 │ (3 sub-agents)│     │ StateAgent   │     │ BoundaryDet  │     │ (4 sub-comp) │
 │               │     │ (FSM parser) │     │ PartBuilder  │     │              │
 │ FATAL on fail │     │ checkpoints  │     │ +LLM fallbk  │     │ GMM τ=0.72  │
 └──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
         │                                                              │
 ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
 │ risk_routing  │────▶│ persist_index│────▶│ translation  │────▶│    merge      │──▶ END
 │   (L2-D)      │     │   (L2-E)     │     │    (L3)      │     │    (L4)      │
 │               │     │              │     │              │     │              │
 │ ComplexityAgt │     │ PersistAgt   │     │ TranslPipeline│    │ ScriptMerger │
 │ StrategyAgent │     │ IndexAgent   │     │ TranslAgent  │     │ ImportConsol │
 │               │     │ NetworkX SCC │     │ ValidateAgt  │     │ DepInjector  │
 │ 14 features   │     │ Tarjan algo  │     │ Z3 + CDAIS   │     │ ReportAgent  │
 │ LogReg+Platt  │     │              │     │ MIS + sandbox│     │ NamespaceChk │
 └──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

#### Error Handling Philosophy

| Node | On Failure | Reason |
|------|-----------|--------|
| `file_process` | **FATAL** — `RuntimeError` raised | Without file metadata, nothing downstream can work |
| `streaming` | Non-fatal — append to `state["errors"]` | Partial parse still useful |
| `chunking` | Non-fatal | Some boundaries may be detected |
| `raptor` | Non-fatal — fallback to flat leaf tree | Flat retrieval still works |
| `risk_routing` | Non-fatal — default to UNCERTAIN | Will route to HUMAN_REVIEW |
| `persist_index` | Non-fatal | Translation can work without persistence |
| `translation` | Non-fatal — PARTIAL status per block | Always get some output |
| `merge` | Non-fatal | Report with partial results |

### `backend/partition/orchestration/state.py` — Pipeline State

#### PipelineStage Enum (14 values)

```
 INIT → FILE_SCAN → CROSS_FILE_RESOLVE → STREAMING → BOUNDARY_DETECTION
   → RAPTOR_CLUSTERING → COMPLEXITY_ANALYSIS → STRATEGY_ASSIGNMENT
     → PERSISTENCE → INDEXING → TRANSLATION → VALIDATION → COMPLETE
                                                              └── ERROR
```

#### PipelineState TypedDict (27 fields)

| Field | Type | Set By | Purpose |
|-------|------|--------|---------|
| `input_paths` | `list[str]` | Input | SAS file paths to process |
| `target_runtime` | `str` | Input | Always `"python"` |
| `stage` | `str` | Each node | Current pipeline stage |
| `current_file_idx` | `int` | Node 1-2 | Index into input_paths |
| `file_metas` | `list[FileMetadata]` | Node 1 | Scanned file metadata |
| `file_ids` | `list[str]` | Node 1 | UUID strings for each file |
| `cross_file_deps` | `dict` | Node 1 | Inter-file dependency map |
| `chunks_by_file` | `dict` | Node 2-3 | Parsed chunks per file |
| `partitions` | `list[PartitionIR]` | Node 3 | All partition objects |
| `partition_count` | `int` | Node 3 | Total partitions created |
| `raptor_nodes` | `list[RAPTORNode]` | Node 4 | RAPTOR tree nodes |
| `complexity_computed` | `bool` | Node 5 | Flag after scoring |
| `scc_groups` | `list` | Node 6 | Strongly connected components |
| `max_hop` | `int` | Node 6 | Max graph traversal depth (1-20) |
| `persisted_count` | `int` | Node 6 | Blocks written to SQLite |
| `conversion_results` | `list[ConversionResult]` | Node 7 | Translation outputs |
| `validation_passed` | `int` | Node 7 | Count of validated blocks |
| `namespace_violations` | `list[str]` | Node 7 | MIS violations found |
| `merge_results` | `list` | Node 8 | Final merged scripts |
| `last_checkpoint_block` | `int` | Checkpoint | Last checkpointed block |
| `checkpoint_key` | `str?` | Checkpoint | Redis checkpoint key |
| `errors` | `list[str]` | Any node | Accumulated error messages |
| `warnings` | `list[str]` | Any node | Accumulated warnings |
| `trace_id` | `str` | Orchestrator | UUID for distributed tracing |
| `run_id` | `str` | Orchestrator | UUID for this run |
| `pipeline_version` | `str` | Orchestrator | `"3.1.0"` |

### Agent Caching Pattern

The orchestrator caches agent instances via `_get_agent(key, factory)`:

```python
def _get_agent(self, key: str, factory: callable):
    if key not in self._agents:
        self._agents[key] = factory()
    return self._agents[key]

# Usage in a node:
agent = self._get_agent("file_processor", lambda: FileProcessor(trace_id=trace_id))
```

This ensures each agent (which may load ML models, open DB connections, or spin up LLM clients) is only instantiated once per pipeline run.

### DuckDB Audit Schema (3 Tables)

#### Table: `llm_audit`

| Column | Type | Description |
|--------|------|-------------|
| `call_id` | VARCHAR | UUID per LLM call |
| `agent_name` | VARCHAR | Which agent made the call |
| `model_name` | VARCHAR | LLM model used |
| `prompt_hash` | VARCHAR | SHA256[:16] of prompt |
| `response_hash` | VARCHAR | SHA256[:16] of response |
| `latency_ms` | DOUBLE | Call duration |
| `success` | BOOLEAN | Whether call succeeded |
| `error_msg` | VARCHAR | Error if failed |
| `tier` | VARCHAR | LLM tier used |
| `created_at` | TIMESTAMP | Auto-set to NOW() |

#### Table: `conversion_results`

| Column | Type | Description |
|--------|------|-------------|
| `conversion_id` | VARCHAR | Links to ConversionRow |
| `block_id` | VARCHAR | Partition UUID |
| `file_id` | VARCHAR | Source file UUID |
| `python_code` | VARCHAR | Translated code |
| `imports_detected` | VARCHAR | Module names |
| `status` | VARCHAR | SUCCESS/PARTIAL/FAILED |
| `llm_confidence` | DOUBLE | LLM self-confidence |
| `failure_mode_flagged` | VARCHAR | Detected failure mode |
| `model_used` | VARCHAR | Which LLM model |
| `kb_examples_used` | VARCHAR | KB example IDs |
| `retry_count` | INTEGER | Number of retries |
| `trace_id` | VARCHAR | Trace UUID |

#### Table: `kb_changelog`

| Column | Type | Description |
|--------|------|-------------|
| `changelog_id` | VARCHAR | UUID |
| `example_id` | VARCHAR | KB entry UUID |
| `action` | VARCHAR | add/edit/rollback/delete |
| `changed_by` | VARCHAR | User who made the change |
| `description` | VARCHAR | What changed |
| `created_at` | TIMESTAMP | Auto-set |

### Redis Checkpoint Mechanism

```
 ┌─────────────────────────────────────────────────────────────┐
 │  RedisCheckpointManager                                     │
 │                                                             │
 │  CHECKPOINT_INTERVAL = 50 blocks                            │
 │  TTL_SECONDS = 86400 (24 hours)                             │
 │                                                             │
 │  Key format: partition:{file_id}:checkpoint:{block_num}     │
 │                                                             │
 │  ┌─────────────────────────────────────────────────────┐    │
 │  │ save_checkpoint(file_id, block_num, partition_data)  │    │
 │  │   IF block_num % 50 != 0: return False (skip)        │    │
 │  │   IF not available: return False (degraded mode)     │    │
 │  │   value = JSON({ file_id, block_num, count, data })  │    │
 │  │   redis.setex(key, 86400, value)                     │    │
 │  └─────────────────────────────────────────────────────┘    │
 │                                                             │
 │  ┌─────────────────────────────────────────────────────┐    │
 │  │ find_latest_checkpoint(file_id)                      │    │
 │  │   keys = redis.keys("partition:{id}:checkpoint:*")   │    │
 │  │   return max(keys, key=block_num)                    │    │
 │  └─────────────────────────────────────────────────────┘    │
 │                                                             │
 │  ┌─────────────────────────────────────────────────────┐    │
 │  │ clear_checkpoints(file_id)                           │    │
 │  │   Delete all keys for completed file                 │    │
 │  └─────────────────────────────────────────────────────┘    │
 │                                                             │
 │  Degraded mode: If Redis unavailable at __init__,           │
 │    self.available = False → all methods become no-ops       │
 └─────────────────────────────────────────────────────────────┘
```

---

## 7. Node 1: File Processing (L2-A)

### Internal Flow

```
 ┌──────────────────────────────────────────────────────┐
 │  FileProcessor.process(input_paths, engine)           │
 │                                                      │
 │  Step 1: Scan Files                                  │
 │  ┌────────────────────────────────────────────┐      │
 │  │ FileAnalysisAgent.process(dir_path)        │      │
 │  │   For each .sas file in directory:         │      │
 │  │   ├── Read file content                    │      │
 │  │   ├── Detect encoding                      │      │
 │  │   ├── Count lines                          │      │
 │  │   ├── Check for %MACRO → has_macros        │      │
 │  │   ├── Check for %INCLUDE → has_includes    │      │
 │  │   ├── Check for PROC SQL → has_sql         │      │
 │  │   ├── Extract dataset refs (DATA/SET/MERGE)│      │
 │  │   ├── Extract LIBNAME references           │      │
 │  │   └── Return FileMetadata                  │      │
 │  └────────────────────────────────────────────┘      │
 │                                                      │
 │  Step 2: Register in SQLite                          │
 │  ┌────────────────────────────────────────────┐      │
 │  │ RegistryWriterAgent.process(metas, engine) │      │
 │  │   Insert/update FileMetadata records       │      │
 │  └────────────────────────────────────────────┘      │
 │                                                      │
 │  Step 3: Resolve Cross-File Dependencies             │
 │  ┌────────────────────────────────────────────┐      │
 │  │ CrossFileDepsResolver.process(metas, root) │      │
 │  │   For each file pair:                      │      │
 │  │   ├── Compare produced vs consumed datasets│      │
 │  │   ├── Build dependency graph               │      │
 │  │   ├── Detect circular dependencies         │      │
 │  │   └── Return { file_id → [dep_file_ids] }  │      │
 │  └────────────────────────────────────────────┘      │
 │                                                      │
 │  Returns: (file_metas: list, cross_deps: dict)       │
 └──────────────────────────────────────────────────────┘
```

### FileMetadata Data Model

| Field | Type | Example |
|-------|------|---------|
| `file_id` | UUID | `a3b2c1d4-...` |
| `file_path` | str | `/uploads/file-abc123/program.sas` |
| `file_name` | str | `program.sas` |
| `file_size` | int | `15420` |
| `line_count` | int | `342` |
| `encoding` | str | `utf-8` |
| `has_macros` | bool | `True` |
| `has_includes` | bool | `False` |
| `has_sql` | bool | `True` |

---

## 8. Node 2: Streaming Parser (L2-B)

### Producer-Consumer Architecture

```
 ┌─────────────────────────────────────────────────────────────┐
 │  run_streaming_pipeline(file_path, file_id)                  │
 │                                                             │
 │  ┌──────────────┐   asyncio.Queue   ┌──────────────────┐   │
 │  │ StreamAgent   │   (bounded=100)   │    StateAgent     │   │
 │  │ (Producer)    │─── LineChunk ────▶│    (Consumer)     │   │
 │  │               │                   │                   │   │
 │  │ Reads file    │   Backpressure:   │ FSM parser        │   │
 │  │ line-by-line  │   If queue full,  │ 12 regex rules    │   │
 │  │               │   producer blocks │ No LLM/network    │   │
 │  │ Wraps lines   │                   │                   │   │
 │  │ into chunks   │                   │ Tracks:           │   │
 │  │ with metadata │                   │ - block type      │   │
 │  │               │                   │ - nesting depth   │   │
 │  │ Sends SENTINEL│                   │ - macro stack     │   │
 │  │ when done     │                   │ - variable scope  │   │
 │  └──────────────┘                   │ - dependencies    │   │
 │                                     │ - comments/strings│   │
 │                                     └──────────────────┘   │
 └─────────────────────────────────────────────────────────────┘
```

### StateAgent FSM (Finite State Machine) — Detailed Rules

The `StateAgent` is a **pure-Python** parser — no LLM, no I/O, no network. It uses 12+ compiled regex patterns to identify SAS constructs:

| Regex Pattern | Compiled Name | What It Matches |
|---------------|---------------|-----------------|
| `^\s*DATA\s+` | `DATA_START` | DATA step opening |
| `^\s*PROC\s+` | `PROC_START` | Any PROC statement |
| `^\s*PROC\s+SQL\b` | `PROC_SQL` | PROC SQL specifically |
| `^\s*PROC\s+(\w+)` | `PROC_NAME` | Extracts PROC name |
| `^\s*%MACRO\s+(\w+)` | `MACRO_DEF` | Macro definition |
| `^\s*%MEND\b` | `MACRO_END` | Macro end |
| `%(?!MACRO\|MEND\|DO\|...)(\w+)\s*[\(;]` | `MACRO_CALL` | Macro invocation |
| `%DO\b` | `DO_START` | Macro DO loop |
| `%IF\b` | `IF_START` | Macro IF conditional |
| `%END\b` | `END_STMT` | Macro block end |
| `^\s*RUN\s*;` | `RUN_STMT` | RUN statement |
| `^\s*QUIT\s*;` | `QUIT_STMT` | QUIT statement |
| `%INCLUDE\s+` | `INCLUDE` | %INCLUDE reference |
| `^\s*(?:OPTIONS\|LIBNAME\|...)` | `GLOBAL` | Global statements |

### Block Closure Rules

```
 ┌─────────────────────────────────────────────────────────────┐
 │  Explicit Closure (keyword-terminated):                      │
 │                                                             │
 │  DATA_STEP  ──── closed by ──── RUN;                         │
 │  PROC_BLOCK ──── closed by ──── RUN; or QUIT;                │
 │  SQL_BLOCK  ──── closed by ──── QUIT;                         │
 │  MACRO_DEF  ──── closed by ──── %MEND;                        │
 │  COND_BLOCK ──── closed by ──── %END;                         │
 │  LOOP_BLOCK ──── closed by ──── %END;                         │
 │                                                             │
 │  Implicit Closure (SAS allows omitting RUN;):                │
 │                                                             │
 │  Open DATA_STEP + new DATA → close old, open new             │
 │  Open DATA_STEP + new PROC → close old, open PROC            │
 │  Open PROC_BLOCK + new DATA → close old, open DATA           │
 │  Open PROC_BLOCK + new PROC → close old, open new PROC       │
 │                                                             │
 │  Never implicitly closed:                                    │
 │  MACRO_DEFINITION, CONDITIONAL_BLOCK, LOOP_BLOCK             │
 │  (they MUST have explicit %MEND / %END)                      │
 └─────────────────────────────────────────────────────────────┘
```

### Known PROC Types (100+ recognized)

The StateAgent recognizes 100+ PROC names organized by category:

| Category | PROCs |
|----------|-------|
| **Base SAS** | SORT, MEANS, FREQ, PRINT, CONTENTS, DATASETS, APPEND, COPY, COMPARE, TRANSPOSE, FORMAT, REPORT, TABULATE, UNIVARIATE, TEMPLATE |
| **SAS/STAT** | REG, LOGISTIC, GLM, MIXED, GENMOD, ANOVA, LIFETEST, PHREG, ARIMA, FACTOR, CLUSTER, TTEST, CORR, STEPWISE, GLIMMIX, LASSO |
| **SAS/ACCESS** | SQL, FEDSQL |
| **SAS/GRAPH** | GCHART, GPLOT, BOXPLOT, SGPLOT, SGPANEL |
| **Import/Export** | IMPORT, EXPORT, CIMPORT, CPORT |

---

## 9. Node 3: Chunking / Boundary Detection (L2-C)

### Hybrid Detection System

```
 ┌──────────────────────────────────────────────────────────────┐
 │  ChunkingAgent.process(chunks_by_file)                       │
 │                                                             │
 │  ┌─────────────────────────────────────────────────────┐    │
 │  │  BoundaryDetector.detect(chunks)                     │    │
 │  │                                                     │    │
 │  │  ┌─────────────────────────┐  ~80% of cases          │    │
 │  │  │ Deterministic Detection │                         │    │
 │  │  │  Lark grammar parser    │                         │    │
 │  │  │  + regex patterns       │                         │    │
 │  │  │                         │  Matches?               │    │
 │  │  └───────────┬─────────────┘   YES → boundary found  │    │
 │  │              │                 NO ↓                   │    │
 │  │  ┌───────────▼─────────────┐  ~20% of cases          │    │
 │  │  │  LLM Boundary Resolver  │                         │    │
 │  │  │  Azure GPT-4o-mini      │                         │    │
 │  │  │  instructor structured  │                         │    │
 │  │  │  Pydantic output model  │                         │    │
 │  │  └─────────────────────────┘                         │    │
 │  └─────────────────────────────────────────────────────┘    │
 │                                                             │
 │  ┌─────────────────────────────────────────────────────┐    │
 │  │  PartitionBuilder.build(boundaries)                  │    │
 │  │    For each detected boundary:                       │    │
 │  │    ├── Generate block_id = UUID4                     │    │
 │  │    ├── Extract source_code text                      │    │
 │  │    ├── Set line_start, line_end                      │    │
 │  │    ├── Set partition_type from boundary              │    │
 │  │    ├── Set risk_level = UNCERTAIN (refined later)    │    │
 │  │    └── Return PartitionIR                            │    │
 │  └─────────────────────────────────────────────────────┘    │
 └──────────────────────────────────────────────────────────────┘
```

### PartitionIR Data Model (Core Unit of Work)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `block_id` | UUID | `uuid4()` | Unique block identifier |
| `file_id` | UUID | required | Source file reference |
| `partition_type` | PartitionType | required | Block classification |
| `source_code` | str | required | Raw SAS code |
| `line_start` | int | required | First line in file |
| `line_end` | int | required | Last line in file |
| `risk_level` | RiskLevel | `UNCERTAIN` | Complexity assessment |
| `conversion_status` | ConversionStatus | `HUMAN_REVIEW` | Translation status |
| `dependencies` | list[UUID] | `[]` | Other block UUIDs |
| `metadata` | dict | `{}` | Arbitrary extra data |
| `created_at` | datetime | `now(UTC)` | Creation time |
| `raptor_leaf_id` | str? | `None` | RAPTOR leaf node ID |
| `raptor_cluster_id` | str? | `None` | RAPTOR cluster ID |
| `raptor_root_id` | str? | `None` | RAPTOR root node ID |

### PartitionType Enum (10 values)

| Value | Weight | SAS Construct |
|-------|--------|---------------|
| `DATA_STEP` | 1.2 | `DATA ... ; ... RUN;` |
| `PROC_BLOCK` | 1.0 | `PROC SORT/MEANS/FREQ/...` |
| `SQL_BLOCK` | 2.0 | `PROC SQL; ... QUIT;` |
| `MACRO_DEFINITION` | 2.5 | `%MACRO name; ... %MEND;` |
| `MACRO_INVOCATION` | 1.0 | `%macroname(...)` |
| `CONDITIONAL_BLOCK` | 1.8 | `%IF ... %THEN ... %END;` |
| `LOOP_BLOCK` | 1.8 | `%DO ... %END;` |
| `GLOBAL_STATEMENT` | 0.2 | `OPTIONS`, `LIBNAME`, `%LET` |
| `INCLUDE_REFERENCE` | 0.3 | `%INCLUDE ...` |
| `UNCLASSIFIED` | 0.8 | Ambiguous blocks |

---

## 10. Node 4: RAPTOR Semantic Clustering (L2-C)

### What is RAPTOR?

RAPTOR (Recursive Abstractive Processing for Tree-Organized Retrieval) clusters semantically related SAS partitions into a hierarchical tree. Instead of flat keyword search, RAPTOR enables hierarchical retrieval: broad context from upper levels, specific details from leaves.

### RAPTOR Pipeline Schema

```
 ┌───────────────────────────────────────────────────────────────────┐
 │  RAPTORPartitionAgent.process(partitions, file_id)                │
 │                                                                   │
 │  Step 1: Embed                                                    │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ NomicEmbedder (nomic-embed-text-v1.5)               │          │
 │  │   Input:  SAS source code (string)                  │          │
 │  │   Output: 768-dimensional float32 vector            │          │
 │  │   Model:  ~270MB, CPU via PyTorch                   │          │
 │  │   Singleton: get_embedder() returns cached instance │          │
 │  │   Prefix: "search_document: " (for doc embeddings)  │          │
 │  │           "search_query: " (for query embeddings)   │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                         ▼                                         │
 │  Step 2: Cluster                                                  │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ GMMClusterer (Gaussian Mixture Model)               │          │
 │  │                                                     │          │
 │  │ Parameters:                                         │          │
 │  │   k = max(2, sqrt(N))     — auto component count   │          │
 │  │   tau (τ) = 0.72          — soft assignment cutoff  │          │
 │  │   BIC_EPSILON = 0.01      — convergence threshold   │          │
 │  │   covariance_type = "full"                          │          │
 │  │   max_iter = 200                                    │          │
 │  │   n_init = 3              — multiple initializations│          │
 │  │   reg_covar = 1e-5        — prevent singular cov    │          │
 │  │   MAX_RETRIES = 3         — retry on convergence    │          │
 │  │                                                     │          │
 │  │ Soft Assignment:                                    │          │
 │  │   For each sample:                                  │          │
 │  │     IF P(cluster|sample) >= 0.72: assign            │          │
 │  │     ELSE: assign to argmax(P) (best cluster)        │          │
 │  │                                                     │          │
 │  │ A block CAN belong to multiple clusters             │          │
 │  │ (e.g., date-handling + merge-semantics)             │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                         ▼                                         │
 │  Step 3: Summarize                                                │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ ClusterSummarizer                                   │          │
 │  │   3-tier fallback:                                  │          │
 │  │     Azure GPT-4o → Groq → extractive heuristic     │          │
 │  │   Produces natural-language summary per cluster     │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                         ▼                                         │
 │  Step 4: Build Tree                                               │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ RAPTORTreeBuilder.build_tree(partitions, file_id)   │          │
 │  │                                                     │          │
 │  │   Level 0 (leaves): each partition = one leaf node  │          │
 │  │   Level 1: clusters of leaves + summaries           │          │
 │  │   Level 2+: recursive clustering of summaries       │          │
 │  │   Until: single root node or BIC converges          │          │
 │  │                                                     │          │
 │  │   Macro density → depth control:                    │          │
 │  │     High macro density → deeper tree (more levels)  │          │
 │  │     Low macro density → shallower tree              │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                                                                   │
 │  Output: list[RAPTORNode] (leaf + cluster + root nodes)           │
 └───────────────────────────────────────────────────────────────────┘
```

### RAPTORNode Data Model

| Field | Type | Description |
|-------|------|-------------|
| `node_id` | UUID | Unique node identifier |
| `level` | int | 0=leaf, 1+=cluster, max=root |
| `summary` | str | Natural language summary |
| `summary_tier` | str | `"groq"/"ollama_fallback"/"heuristic_fallback"/"cached"` |
| `embedding` | list[float] | 768-dim vector |
| `child_ids` | list[str] | Children node IDs |
| `cluster_label` | int? | GMM cluster assignment |
| `file_id` | UUID | Source file |
| `partition_ids` | list[str] | Leaf partition IDs |

### Example RAPTOR Tree

```
                    ┌─────────────┐
                    │   Root (L2)  │
                    │ "This file   │
                    │  handles ETL │
                    │  + reporting"│
                    └──────┬──────┘
                ┌──────────┴──────────┐
        ┌───────┴───────┐     ┌───────┴───────┐
        │ Cluster A (L1)│     │ Cluster B (L1)│
        │ "Data loading │     │ "Statistical  │
        │  and cleanup" │     │  analysis"    │
        └───────┬───────┘     └───────┬───────┘
     ┌──────┬───┴───┐           ┌─────┴──────┐
     ▼      ▼       ▼           ▼            ▼
  Leaf 1  Leaf 2  Leaf 3     Leaf 4       Leaf 5
  DATA    DATA    PROC       PROC         PROC
  STEP    STEP    SQL        MEANS        REG
```

---

## 11. Node 5: Risk Routing / Complexity Scoring (L2-D)

### ComplexityAgent — ML + Rule-Based Scoring

```
 ┌───────────────────────────────────────────────────────────────────┐
 │  ComplexityAgent.process(partitions)                               │
 │                                                                   │
 │  For each PartitionIR:                                            │
 │                                                                   │
 │  Step 1: Extract 14 Features                                      │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │  features.extract(partition) → BlockFeatures        │          │
 │  │                                                     │          │
 │  │  6 Structural:          8 SAS-Specific:             │          │
 │  │  ├── line_count_norm    ├── has_retain_first_last   │          │
 │  │  ├── nesting_depth_norm ├── has_merge_hash          │          │
 │  │  ├── macro_pct          ├── has_sql_subquery        │          │
 │  │  ├── has_call_execute   ├── has_array_loop          │          │
 │  │  ├── type_weight        ├── dataset_count_norm      │          │
 │  │  └── is_ambiguous       ├── has_call_symput         │          │
 │  │                         ├── conditional_density     │          │
 │  │                         └── has_complex_proc        │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                                                                   │
 │  Step 2: Classify Risk                                            │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │  IF ML model fitted:                                │          │
 │  │    CalibratedClassifierCV(LogReg, method="sigmoid") │          │
 │  │    Trained on gold corpus (721 blocks, 3 tiers)     │          │
 │  │    ECE target < 0.08                                │          │
 │  │    Output: predicted RiskLevel + confidence          │          │
 │  │                                                     │          │
 │  │  ELSE (rule-based fallback):                        │          │
 │  │    Apply ~20 prioritized rules (see table below)    │          │
 │  └─────────────────────────────────────────────────────┘          │
 └───────────────────────────────────────────────────────────────────┘
```

### 14 Features Detail Table

| # | Feature | Normalization | Description |
|---|---------|---------------|-------------|
| 1 | `line_count_norm` | lines / 200 | Block size indicator |
| 2 | `nesting_depth_norm` | depth / 5 | DO/IF nesting complexity |
| 3 | `macro_pct` | `%` count / lines, cap 1.5 | Macro density |
| 4 | `has_call_execute` | 0 or 1 | CALL EXECUTE (dynamic code gen) |
| 5 | `type_weight` | 0.2 – 2.5 | Partition type weight |
| 6 | `is_ambiguous` | 0 or 1 | Parser flagged as ambiguous |
| 7 | `has_retain_first_last` | 0 or 1 | RETAIN or FIRST./LAST. pattern |
| 8 | `has_merge_hash` | 0 or 1 | MERGE or hash object |
| 9 | `has_sql_subquery` | 0 or 1 | Nested SELECT in PROC SQL |
| 10 | `has_array_loop` | 0 or 1 | ARRAY or complex DO loops |
| 11 | `dataset_count_norm` | count / 5, cap 1.5 | Distinct dataset references |
| 12 | `has_call_symput` | 0 or 1 | CALL SYMPUT/SYMPUTX |
| 13 | `conditional_density` | IF-THEN count / lines, cap 1.0 | Branch density |
| 14 | `has_complex_proc` | 0 or 1 | PROC TRANSPOSE or PROC REPORT |

### Rule-Based Risk Classification

| Priority | Pattern | Risk Score | Risk Level |
|----------|---------|------------|------------|
| 1 | `CALL EXECUTE` | 0.92 | HIGH |
| 2 | SQL subquery `(SELECT...)` | 0.88 | HIGH |
| 3 | `MERGE` + `RETAIN` | 0.87 | HIGH |
| 4 | `CALL SYMPUT` / `SYMPUTX` | 0.85 | HIGH |
| 5 | Nesting depth >= 3 | 0.84 | HIGH |
| 6 | Lines >= 80 | 0.78 | HIGH |
| 7 | `RETAIN` alone | 0.80 | MODERATE |
| 8 | `MERGE` alone | 0.78 | MODERATE |
| 9 | `ARRAY` | 0.76 | MODERATE |
| 10 | Nesting depth >= 2 | 0.75 | MODERATE |
| 11 | Hash objects | 0.82 | HIGH |
| 12 | `PROC TRANSPOSE/REPORT` | 0.74 | MODERATE |
| Default | Small code + simple type | < 0.50 | LOW |

### StrategyAgent — Routing Table

```
 ┌──────────┬────────────────────┬──────────────────────────┐
 │Risk Level│ Partition Type     │ Strategy Assigned        │
 ├──────────┼────────────────────┼──────────────────────────┤
 │          │ DATA_STEP          │ FLAT_PARTITION           │
 │   LOW    │ PROC_BLOCK         │ FLAT_PARTITION           │
 │          │ SQL_BLOCK           │ DEPENDENCY_PRESERVING    │
 │          │ MACRO_*            │ MACRO_AWARE              │
 │          │ GLOBAL/INCLUDE     │ FLAT_PARTITION           │
 ├──────────┼────────────────────┼──────────────────────────┤
 │          │ DATA_STEP          │ DEPENDENCY_PRESERVING    │
 │ MODERATE │ PROC_BLOCK/SQL     │ DEPENDENCY_PRESERVING    │
 │          │ MACRO_*            │ MACRO_AWARE              │
 │          │ GLOBAL/INCLUDE     │ FLAT_PARTITION           │
 ├──────────┼────────────────────┼──────────────────────────┤
 │   HIGH   │ (any type)         │ STRUCTURAL_GROUPING      │
 ├──────────┼────────────────────┼──────────────────────────┤
 │UNCERTAIN │ (any type)         │ HUMAN_REVIEW             │
 └──────────┴────────────────────┴──────────────────────────┘
```

---

## 12. Node 6: Persistence + Indexing (L2-E)

### Dependency Graph Construction

```
 ┌───────────────────────────────────────────────────────┐
 │  PersistenceAgent → writes all PartitionIR to SQLite  │
 │                                                       │
 │  IndexAgent → builds NetworkX directed graph           │
 │                                                       │
 │  ┌─────────────────────────────────────────────────┐  │
 │  │  NetworkXGraphBuilder.build(partitions)          │  │
 │  │                                                 │  │
 │  │  Nodes: each PartitionIR (keyed by block_id)    │  │
 │  │  Edges: block A depends on block B              │  │
 │  │         (A reads a dataset B creates)            │  │
 │  │                                                 │  │
 │  │  SCC Detection: Tarjan's algorithm              │  │
 │  │    Circular dependencies → batched translation   │  │
 │  │    Example: macro A calls macro B, B calls A     │  │
 │  │    All SCC members translated together           │  │
 │  │                                                 │  │
 │  │  Topological Sort: determines translation order  │  │
 │  │    Dependencies translated before dependents     │  │
 │  └─────────────────────────────────────────────────┘  │
 └───────────────────────────────────────────────────────┘
```

---

## 13. Node 7: Translation (L3) — The Core

This is the most complex node. It translates every SAS partition into Python code with multi-layer verification.

### Translation Pipeline Per-Partition Flow

```
 ┌───────────────────────────────────────────────────────────────────────┐
 │  TranslationPipeline.translate_partition(partition)                    │
 │                                                                       │
 │  ┌────────────────────────────────────────────────┐                   │
 │  │ asyncio.wait_for(timeout=120s)                  │                   │
 │  │   └── _translate_partition_inner(partition)      │                   │
 │  └────────────────────────────────────────────────┘                   │
 │                                                                       │
 │  Step 0a: Translation Memory Cache                                    │
 │  ┌────────────────────────────────────────────────┐                   │
 │  │ Check semantic fingerprint cache                │                   │
 │  │ IF cache hit: return cached code (skip LLM)     │                   │
 │  └────────────────────────────────────────────────┘                   │
 │                                                                       │
 │  Step 0b: Macro Expansion                                             │
 │  ┌────────────────────────────────────────────────┐                   │
 │  │ expand_macros(source_code)                      │                   │
 │  │ Resolve %LET variables before translation       │                   │
 │  └────────────────────────────────────────────────┘                   │
 │                                                                       │
 │  Step 0c: Deterministic Shortcut (No LLM)                             │
 │  ┌────────────────────────────────────────────────┐                   │
 │  │ try_deterministic(expanded_sas)                 │                   │
 │  │ Pattern-matched translations:                   │                   │
 │  │   PROC PRINT → print(df)                        │                   │
 │  │   PROC SORT  → df.sort_values(...)              │                   │
 │  │   %LET       → variable assignment              │                   │
 │  │ IF matched: return immediately (confidence=1.0) │                   │
 │  └────────────────────────────────────────────────┘                   │
 │                                                                       │
 │  Step 1: Failure Mode Detection (6 rules)                             │
 │  ┌────────────────────────────────────────────────┐                   │
 │  │ detect_failure_mode(sas_code)                   │                   │
 │  │ get_combined_failure_mode_rules(sas_code)       │                   │
 │  │ Returns: detected pattern + repair rules        │                   │
 │  └────────────────────────────────────────────────┘                   │
 │                                                                       │
 │  Step 2: Business Logic Enrichment                                    │
 │  ┌────────────────────────────────────────────────┐                   │
 │  │ ├── get_format_hint_block(sas)  → SAS format map│                   │
 │  │ ├── get_builtins_hint_block(sas) → INTCK/INTNX │                   │
 │  │ ├── infer_types(sas)            → type report   │                   │
 │  │ └── macro_report.to_prompt_block()              │                   │
 │  └────────────────────────────────────────────────┘                   │
 │                                                                       │
 │  Step 3: RAG Router → Build Prompt                                    │
 │  ┌────────────────────────────────────────────────┐                   │
 │  │ rag_router.build_context(partition, ...)        │                   │
 │  │   select_paradigm() → "static"/"graph"/"agentic"│                   │
 │  │   Retrieve KB examples via LanceDB              │                   │
 │  │   Render Jinja2 prompt template                  │                   │
 │  │   Returns: { prompt, kb_examples, paradigm }     │                   │
 │  └────────────────────────────────────────────────┘                   │
 │                                                                       │
 │  Step 4: LLM Translation (Fallback Chain)                             │
 │  ┌────────────────────────────────────────────────┐                   │
 │  │ Try Tier 0: Local GGUF (LOW risk only)          │                   │
 │  │ Try Tier 1: Azure GPT-4o / 4o-mini              │                   │
 │  │ Try Tier 2: Ollama nemotron-3-super:cloud        │                   │
 │  │ Try Tier 3: Groq LLaMA-3.3-70B                  │                   │
 │  │ If all fail: return PARTIAL status               │                   │
 │  │                                                 │                   │
 │  │ Output: TranslationOutput (python_code,          │                   │
 │  │         imports, confidence, notes)               │                   │
 │  └────────────────────────────────────────────────┘                   │
 │                                                                       │
 │  Step 5: Cross-Verification (Prompt C)                                │
 │  ┌────────────────────────────────────────────────┐                   │
 │  │ Send (SAS, Python) to DIFFERENT LLM provider    │                   │
 │  │ CrossVerifyOutput: { equivalent, confidence,     │                   │
 │  │                      issues }                    │                   │
 │  │ IF confidence < 0.75: trigger reflexion retry    │                   │
 │  └────────────────────────────────────────────────┘                   │
 │                                                                       │
 │  VALIDATION LOOP:                                                     │
 │  ┌────────────────────────────────────────────────┐                   │
 │  │ ValidationAgent.validate(conversion)            │                   │
 │  │   ├── ast.parse() → syntax check                │                   │
 │  │   └── exec() sandbox → runtime check            │                   │
 │  │                                                 │                   │
 │  │ IF validation fails:                             │                   │
 │  │   ├── classify_error() → SYNTAX or SEMANTIC      │                   │
 │  │   ├── analyse_error() → repair hints             │                   │
 │  │   ├── Inject error context into prompt           │                   │
 │  │   ├── Retry (budget: 2 + 1 for MACRO/SQL         │                   │
 │  │   │                + 1 for semantic errors)       │                   │
 │  │   └── Stagnation: stop if 2 identical retries    │                   │
 │  └────────────────────────────────────────────────┘                   │
 │                                                                       │
 │  VERIFICATION:                                                        │
 │  ┌────────────────────────────────────────────────┐                   │
 │  │ Z3VerificationAgent.verify(sas, python)         │                   │
 │  │   11 SMT patterns (see Section 15)               │                   │
 │  │   IF COUNTEREXAMPLE: re-queue at HIGH risk       │                   │
 │  │                                                 │                   │
 │  │ CDAISRunner.run(sas, python)                     │                   │
 │  │   6 adversarial error classes                    │                   │
 │  │   Issue coverage certificates                    │                   │
 │  │                                                 │                   │
 │  │ MIS invariant check (if loaded)                  │                   │
 │  │   12 confirmed invariants                        │                   │
 │  └────────────────────────────────────────────────┘                   │
 │                                                                       │
 │  Output: ConversionResult                                             │
 └───────────────────────────────────────────────────────────────────────┘
```

### Retry Budget Calculation

```python
_BASE_RETRIES = 2
_MACRO_SQL_BONUS = 1       # +1 for MACRO_DEFINITION / SQL_BLOCK
_SEMANTIC_ERROR_BONUS = 1  # +1 when syntax ok but exec fails
_MAX_STAGNANT = 2          # stop if code unchanged 2x in a row

def _retry_budget(partition):
    budget = 2  # base
    if partition_type in ("MACRO_DEFINITION", "MACRO_INVOCATION", "SQL_BLOCK"):
        budget += 1  # total: 3
    # During retry loop, if error is semantic (not syntax): +1 more
    # Maximum possible: 4 retries for a MACRO with semantic error
```

### Validation Sandbox — How It Works Internally

```
 ┌───────────────────────────────────────────────────────────────────┐
 │  ValidationAgent.validate(conversion)                              │
 │                                                                   │
 │  Step 1: Syntax Check                                             │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │  ast.parse(python_code)                             │          │
 │  │  IF SyntaxError: return ValidationResult(           │          │
 │  │    passed=False, syntax_ok=False)                   │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                                                                   │
 │  Step 2: Sandbox Execution                                        │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │  multiprocessing.Queue() ← communication channel    │          │
 │  │  multiprocessing.Process(target=_sandbox_exec)      │          │
 │  │                                                     │          │
 │  │  Inside subprocess:                                 │          │
 │  │  ┌────────────────────────────────────────────┐     │          │
 │  │  │ Blocked builtins:                          │     │          │
 │  │  │   open, exec, eval, compile, exit, quit,   │     │          │
 │  │  │   input, breakpoint, memoryview             │     │          │
 │  │  │                                            │     │          │
 │  │  │ Provided namespace:                        │     │          │
 │  │  │   pd (pandas), np (numpy)                  │     │          │
 │  │  │   df = synthetic 100-row DataFrame         │     │          │
 │  │  │   _AutoNamespace (magic dict):              │     │          │
 │  │  │     ANY undefined variable → auto-DataFrame │     │          │
 │  │  │     with 25+ common columns:               │     │          │
 │  │  │     id, customer_id, amount, revenue,       │     │          │
 │  │  │     score, age, status, category, region,   │     │          │
 │  │  │     date, close, open, high, low, volume... │     │          │
 │  │  │                                            │     │          │
 │  │  │ exec(code, namespace)                       │     │          │
 │  │  │                                            │     │          │
 │  │  │ On success: queue.put({ok:True, stdout,     │     │          │
 │  │  │   exec_states: variable snapshots})         │     │          │
 │  │  │ On error: queue.put({ok:False, error,       │     │          │
 │  │  │   traceback, exec_states: crash snapshot})  │     │          │
 │  │  └────────────────────────────────────────────┘     │          │
 │  │                                                     │          │
 │  │  Timeout: 15s (Windows) / 8s (Linux)                │          │
 │  │  On timeout: process.kill() (not .join())            │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                                                                   │
 │  EGS (Execution-Guided Synthesis):                                │
 │  On failure, captures variable state at crash point:              │
 │  DataFrame shapes, column dtypes, scalar values, stdout           │
 │  → injected into repair prompt for targeted guidance              │
 └───────────────────────────────────────────────────────────────────┘
```

### ConversionResult Data Model

| Field | Type | Description |
|-------|------|-------------|
| `conversion_id` | UUID | Unique for this translation |
| `block_id` | UUID | Source partition |
| `file_id` | UUID | Source file |
| `python_code` | str | Translated Python code |
| `imports_detected` | list[str] | Module names detected |
| `status` | ConversionStatus | SUCCESS/PARTIAL/FAILED/HUMAN_REVIEW |
| `llm_confidence` | float | 0.0 – 1.0 |
| `failure_mode_flagged` | str | Detected failure mode |
| `model_used` | str | Which LLM model |
| `kb_examples_used` | list | KB example IDs used |
| `retry_count` | int | Number of retries |
| `trace_id` | UUID | Trace for debugging |
| `rag_paradigm` | str | static/graph/agentic/deterministic/cache |

---

## 14. Node 8: Merge (L4)

### Merge Pipeline Schema

```
 ┌───────────────────────────────────────────────────────────────────┐
 │  MergeAgent.process(conversion_results, partitions, ...)          │
 │                                                                   │
 │  Step 1: Sort by line_start                                       │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ paired = zip(conversion_results, partitions)        │          │
 │  │ paired.sort(key=lambda p: p[1].line_start)          │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                                                                   │
 │  Step 2: Consolidate Imports                                      │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ ImportConsolidator.consolidate_imports(all_imports)  │          │
 │  │                                                     │          │
 │  │ Canonical Aliases:                                  │          │
 │  │   pandas → import pandas as pd                      │          │
 │  │   numpy  → import numpy as np                       │          │
 │  │   statsmodels → import statsmodels.api as sm        │          │
 │  │   matplotlib → import matplotlib.pyplot as plt      │          │
 │  │                                                     │          │
 │  │ PEP 8 Ordering:                                     │          │
 │  │   Section 1: stdlib (os, sys, re, datetime...)      │          │
 │  │   Section 2: third-party (pandas, numpy, sklearn...)│          │
 │  │   Section 3: local (partition.*)                    │          │
 │  │   Blank line between sections                       │          │
 │  │                                                     │          │
 │  │ Deduplication: same import → only included once     │          │
 │  │ Merging: from X import a + from X import b          │          │
 │  │          → from X import a, b                       │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                                                                   │
 │  Step 3: Build Name Registry + Inject Dependencies                │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ DependencyInjector:                                 │          │
 │  │   If block B reads dataset created by block A,      │          │
 │  │   ensure A's code appears before B in final script  │          │
 │  │                                                     │          │
 │  │ Cross-file stubs for unresolved references          │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                                                                   │
 │  Step 4: Assemble Body                                            │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ For each (conversion, partition) sorted pair:       │          │
 │  │   IF SUCCESS: strip imports, add code block         │          │
 │  │   IF PARTIAL: add code with # PARTIAL comment       │          │
 │  │   IF FAILED/HUMAN_REVIEW: add TODO stub             │          │
 │  │     with original SAS code as commented block       │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                                                                   │
 │  Step 5: Namespace Check                                          │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ check_namespace(merged_code)                        │          │
 │  │   Verify all variables and DataFrames are defined   │          │
 │  │   before use in the merged script                   │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                                                                   │
 │  Step 6: Generate Report                                          │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ ReportAgent.generate_report(...)                    │          │
 │  │   HTML report with:                                 │          │
 │  │   ├── Summary stats (blocks, accuracy, models)      │          │
 │  │   ├── Per-partition details (SAS→Python, confidence) │          │
 │  │   ├── Verification results (Z3, CDAIS)              │          │
 │  │   ├── Failure modes detected                        │          │
 │  │   └── Warnings and errors                           │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                                                                   │
 │  Final Output Format:                                             │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ # ============================================      │          │
 │  │ # Auto-generated by SAS→Python Conversion Accel.    │          │
 │  │ # Source: program.sas                               │          │
 │  │ # Generated: 2026-04-29T10:30:00+00:00              │          │
 │  │ # Target: python                                    │          │
 │  │ # Blocks: 12 total, 1 partial                       │          │
 │  │ # ============================================      │          │
 │  │                                                     │          │
 │  │ import pandas as pd                                 │          │
 │  │ import numpy as np                                  │          │
 │  │                                                     │          │
 │  │ # --- Block 1: DATA_STEP (lines 1-15) ---           │          │
 │  │ df = pd.read_csv('input.csv')                       │          │
 │  │ ...                                                 │          │
 │  │ # --- Block 2: PROC_SORT (lines 16-20) ---          │          │
 │  │ df = df.sort_values('customer_id')                  │          │
 │  │ ...                                                 │          │
 │  └─────────────────────────────────────────────────────┘          │
 └───────────────────────────────────────────────────────────────────┘
```

---

## 15. The Three RAG Paradigms

### RAG Router Decision Logic

```
 ┌─────────────────────────────────────────────────────────────┐
 │  RAGRouter.select_paradigm(partition, attempt, failure_mode) │
 │                                                             │
 │  ┌────────────────────────────────────────────┐             │
 │  │ risk in (MODERATE, HIGH, UNCERTAIN)?        │─── YES ──▶ AGENTIC
 │  └─────────────────────┬──────────────────────┘             │
 │                        │ NO                                  │
 │  ┌─────────────────────▼──────────────────────┐             │
 │  │ failure_mode detected?                      │─── YES ──▶ AGENTIC
 │  └─────────────────────┬──────────────────────┘             │
 │                        │ NO                                  │
 │  ┌─────────────────────▼──────────────────────┐             │
 │  │ attempt_number > 0? (retry)                 │─── YES ──▶ AGENTIC
 │  └─────────────────────┬──────────────────────┘             │
 │                        │ NO                                  │
 │  ┌─────────────────────▼──────────────────────┐             │
 │  │ has SCC membership OR has dependencies?     │─── YES ──▶ GRAPH
 │  └─────────────────────┬──────────────────────┘             │
 │                        │ NO                                  │
 │                        ▼                                     │
 │                     STATIC                                   │
 └─────────────────────────────────────────────────────────────┘
```

### Paradigm Comparison Table

| Feature | Static RAG | GraphRAG | Agentic RAG |
|---------|-----------|----------|-------------|
| **Risk level** | LOW only | Any (with deps) | MODERATE/HIGH/UNCERTAIN |
| **KB examples** | top-k cosine | top-k + dependency context | top-k + deps + escalated k |
| **Graph traversal** | None | Up to 3 hops | Up to 3 hops + SCC |
| **Dependency context** | None | Translated deps included | Deps + previous attempts |
| **Error context** | None | None | Error analysis + reflection |
| **Failure mode rules** | None | None | Injected into prompt |
| **Jinja2 template** | `translation_static.j2` | `translation_graph.j2` | `translation_agentic.j2` |
| **Typical use** | `PROC PRINT`, simple DATA | Multi-file datasets | RETAIN, MERGE, HASH |

---

## 16. LLM Provider Chain & Fallback Mechanism

### Provider Hierarchy (6 Tiers)

| Tier | Provider | Model | Cost | Latency | Use Case |
|------|----------|-------|------|---------|----------|
| 0 | Local GGUF | Fine-tuned Qwen2.5-Coder-7B | Free | ~200ms | LOW risk only |
| 1 | Ollama | minimax-m2.7:cloud | Free | ~2s | PRIMARY (10/10 torture test) |
| 2 | Azure OpenAI | GPT-4o (full) / GPT-4o-mini (mini) | $$$ | ~3s | Fallback 1 (enterprise SLA) |
| 3 | Groq | LLaMA-3.3-70B | Free | ~1s | Fallback 2 + cross-verifier |
| 4 | Gemini | 2.0 Flash | Free | ~2s | Oracle & judge |
| 5 | Cerebras | Llama-3.1-70B | Free | ~0.5s | Best-of-N candidates |
| — | — | — | — | — | PARTIAL status (all exhausted) |

### Strategy Pattern Implementation

```
 ┌─────────────────────────────────────────────────────────────────┐
 │  LLM Client Architecture (Strategy Pattern)                      │
 │                                                                 │
 │  ┌────────────────┐                                             │
 │  │ LLMStrategy    │ ← Abstract Base Class                       │
 │  │  (ABC)         │                                             │
 │  ├────────────────┤                                             │
 │  │ get_client()   │                                             │
 │  │ is_available() │                                             │
 │  │ name           │                                             │
 │  └───────┬────────┘                                             │
 │     ┌────┴────┬────────────┐                                    │
 │     ▼         ▼            ▼                                    │
 │  ┌──────┐  ┌──────┐  ┌──────┐                                  │
 │  │Ollama│  │Azure │  │ Groq │                                  │
 │  │Strat │  │Strat │  │Strat │                                  │
 │  └──────┘  └──────┘  └──────┘                                  │
 │                                                                 │
 │  FallbackChain([OllamaStrategy, AzureStrategy, GroqStrategy])   │
 │    .get_client() → returns first available provider             │
 └─────────────────────────────────────────────────────────────────┘
```

### GroqPool — API Key Rotation

```
 ┌─────────────────────────────────────────────────────────────┐
 │  GroqPool                                                    │
 │                                                             │
 │  Keys: GROQ_API_KEY, GROQ_API_KEY_2, ..., GROQ_API_KEY_9   │
 │  Base URL: https://api.groq.com/openai/v1                   │
 │                                                             │
 │  Each key: 100K tokens/day                                  │
 │  With 3 keys: 300K tokens/day                               │
 │                                                             │
 │  call_with_rotation(model, messages, response_model):       │
 │    FOR key IN round_robin(keys):                            │
 │      TRY: client[key].chat.completions.create(...)          │
 │      ON 429 (rate limit): switch to next key                │
 │      ON success: return result                              │
 └─────────────────────────────────────────────────────────────┘
```

### Risk-Based Model Selection

| Risk Level | Azure Deployment | Reason |
|-----------|-----------------|--------|
| LOW | `gpt-4o-mini` | Cheaper, faster, sufficient for simple blocks |
| MODERATE | `gpt-4o` | More capable for complex patterns |
| HIGH | `gpt-4o` | Maximum capability needed |

---

## 17. Verification Layer

After translation, the code goes through **five independent verification mechanisms**.

### Verification Stack Schema

```
 ┌───────────────────────────────────────────────────────────────────┐
 │  Post-Translation Verification Stack                              │
 │                                                                   │
 │  Layer 1: Syntax Check (ast.parse)                                │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ Parse Python code into AST                          │          │
 │  │ Catches: missing colons, unmatched parens, etc.     │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                                                                   │
 │  Layer 2: Sandbox Execution (subprocess + exec)                   │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ Actually runs the code in isolated process          │          │
 │  │ Catches: NameError, TypeError, import failures      │          │
 │  │ EGS: captures variable state at crash point         │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                                                                   │
 │  Layer 3: Z3 Formal Verification (11 SMT patterns)                │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ Mathematical PROOF of equivalence (not testing)     │          │
 │  │ Catches: wrong operators, missing group resets      │          │
 │  │ COUNTEREXAMPLE → re-queue at HIGH risk              │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                                                                   │
 │  Layer 4: CDAIS Adversarial Testing (6 error classes)             │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ Z3-synthesized minimum witness DataFrames           │          │
 │  │ Catches: RETAIN reset, LAG queue, join type bugs    │          │
 │  │ Issues coverage certificates for passing classes    │          │
 │  └─────────────────────────────────────────────────────┘          │
 │                                                                   │
 │  Layer 5: Cross-Verification (multi-LLM)                          │
 │  ┌─────────────────────────────────────────────────────┐          │
 │  │ Different LLM judges the translation independently  │          │
 │  │ IF confidence < 0.75: trigger reflexion retry        │          │
 │  └─────────────────────────────────────────────────────┘          │
 └───────────────────────────────────────────────────────────────────┘

 Combined Impact:
 ┌─────────────────────────────┬──────────┬──────────────┐
 │ Configuration                │ Accuracy │ Delta        │
 ├─────────────────────────────┼──────────┼──────────────┤
 │ LLM baseline (no validation)│  71.2%   │  —           │
 │ + Execution sandbox         │  78.4%   │  +7.2pp      │
 │ + Z3 verification           │  83.7%   │  +12.5pp     │
 │ + SemanticValidator          │  88.9%   │  +17.7pp     │
 │ + CDAIS                      │  93.6%   │  +22.4pp     │
 │ + MIS                        │  96.1%   │  +24.9pp     │
 └─────────────────────────────┴──────────┴──────────────┘
```

### What Z3 Actually Proves (And What It Can't)

Z3 is Microsoft Research's **SMT solver** (Satisfiability Modulo Theories). It answers: *"Is there ANY possible input where these two programs produce different outputs?"*

- **UNSAT** (no such input exists) → the programs are **provably equivalent** for all possible inputs
- **SAT** → Z3 gives a **concrete counterexample**: specific input values where they differ
- **UNKNOWN** → timeout or too complex for the solver — non-blocking, pipeline continues

Z3 works on **decidable fragments** — mathematical problems with guaranteed termination. Not all SAS code is decidable, so Z3 covers a subset:

| SAS Pattern | What Z3 Proves | Coverage |
|---|---|---|
| `PROC MEANS` / `SUM` / `COUNT` | `mean(x) = sum(x)/N` for all N > 0 | ~71% of arithmetic blocks |
| `WHERE age > 18` / `IF status = 1` | Boolean filter identity | ~64% of filter blocks |
| `PROC SORT NODUPKEY` | output ⊆ input, unique on key | ~48% of sort blocks |
| Simple assignment `new_var = x * 2 + 10` | Linear arithmetic equality | ~60% of assignment blocks |

**Overall provability: ~41% of LOW-risk blocks** get a formal machine-checkable proof. The other 59% get `UNKNOWN` status — **non-blocking**. The pipeline continues normally. Only `COUNTEREXAMPLE` (Z3 found a real semantic difference) blocks the partition — it re-queues with `risk_level = HIGH` and forces a GPT-4o retry with the counterexample in the prompt (CEGAR loop).

### Z3 Verification — 11 SMT Patterns

| # | Pattern | SAS Construct | What Z3 Proves | Counterexample Trigger |
|---|---------|---------------|---------------|----------------------|
| 1 | `conditional_assignment` | IF/THEN/ELSE chains | `cond_sas(x) == cond_py(x)` for symbolic x | `iterrows()` used for column assignment |
| 2 | `sort_direction` | PROC SORT DESCENDING | Direction booleans match BY-clause | Wrong `ascending=` value |
| 3 | `proc_means_groupby` | PROC MEANS CLASS | Single groupby with `dropna=False` | Multiple merged groupbys |
| 4 | `boolean_filter` | WHERE x > 5000 | `filter_sas(x) == filter_py(x)` | Wrong operator or threshold |
| 5 | `format_display_only` | FORMAT/PROC FORMAT | New column created, original preserved | Original column overwritten |
| 6 | `left_join` | LEFT JOIN | `how='left'` used | `how='inner'` or missing |
| 7 | `merge_indicator` | MERGE IN= | `indicator=True` + drop `_merge` | indicator missing or not cleaned |
| 8 | `stepwise_regression` | PROC REG STEPWISE | OLS + p-value loop | sklearn or BIC/AIC used |
| 9 | `sort_nodupkey` | PROC SORT NODUPKEY | `sort_values` + `drop_duplicates` | `drop_duplicates` missing |
| 10 | `simple_assignment` | y = x * c + b | Coefficients match for symbolic x | Coefficient mismatch |
| 11 | `sum_missing_semantics` | SUM() vs + | SUM→nansum (skip NaN), +→bare + (propagate) | SUM() translated as bare + |

### Z3 Pattern Execution Flow

```
 verify(sas_code, python_code):
   │
   ├── FOR each of 11 patterns:
   │     ├── Check applicability (regex on SAS code)
   │     │     IF not applicable: skip (return None)
   │     │
   │     ├── Extract values from SAS and Python with regex
   │     │
   │     ├── Create Z3 symbolic variables
   │     │     x = z3.Int('x')  or  z3.Real('x')
   │     │
   │     ├── Encode SAS semantics as Z3 constraint
   │     │     sas_result = z3.If(x < threshold, val_a, val_b)
   │     │
   │     ├── Encode Python semantics as Z3 constraint
   │     │     py_result = z3.If(x < py_threshold, py_val_a, py_val_b)
   │     │
   │     ├── Ask Z3: EXISTS x WHERE sas_result != py_result?
   │     │     solver.add(sas_result != py_result)
   │     │     result = solver.check()
   │     │
   │     ├── IF SAT → COUNTEREXAMPLE found
   │     │     model = solver.model()
   │     │     return VerificationResult(COUNTEREXAMPLE, ...)
   │     │
   │     ├── IF UNSAT → PROVED (no counterexample exists)
   │     │     return VerificationResult(PROVED, ...)
   │     │
   │     └── IF UNKNOWN → timeout or too complex
   │
   └── Return worst result: COUNTEREXAMPLE > PROVED > UNKNOWN > SKIPPED
```

---

## 18. The Four Databases

### Database Architecture Schema

```
 ┌─────────────────────────────────────────────────────────────────┐
 │                     Codara Data Architecture                     │
 │                                                                 │
 │  ┌──────────────────────┐       ┌──────────────────────┐        │
 │  │  SQLite               │       │  Redis                │        │
 │  │  codara_api.db        │       │  localhost:6379/0     │        │
 │  │                      │       │                      │        │
 │  │  Access: ACID CRUD    │       │  Access: atomic R/W   │        │
 │  │  Mode: WAL            │       │  Purpose: checkpoints │        │
 │  │  Tables: 8            │       │  TTL: 24 hours        │        │
 │  │  Manager: SQLAlchemy  │       │  Degraded: no-op      │        │
 │  │                      │       │                      │        │
 │  │  Users, Conversions,  │       │  Key format:          │        │
 │  │  Stages, KB, Audit,   │       │  partition:{fid}:     │        │
 │  │  Corrections, Notifs  │       │  checkpoint:{block}   │        │
 │  └──────────────────────┘       └──────────────────────┘        │
 │                                                                 │
 │  ┌──────────────────────┐       ┌──────────────────────┐        │
 │  │  LanceDB              │       │  DuckDB               │        │
 │  │  data/lancedb/        │       │  analytics.duckdb     │        │
 │  │                      │       │                      │        │
 │  │  Access: vector cosine│       │  Access: columnar SQL │        │
 │  │  Purpose: RAG search  │       │  Purpose: analytics   │        │
 │  │  Table: sas_python_   │       │  Tables: 3            │        │
 │  │    examples           │       │  Queries: agg, GROUP  │        │
 │  │  Embedding: 768-dim   │       │    BY, time-series    │        │
 │  │  Index: IVF-64 cosine │       │                      │        │
 │  │  Records: 330+ pairs  │       │  llm_audit,           │        │
 │  │                      │       │  conversion_results,  │        │
 │  │  16 fields per entry  │       │  kb_changelog         │        │
 │  └──────────────────────┘       └──────────────────────┘        │
 └─────────────────────────────────────────────────────────────────┘
```

### Why 4 Databases?

| Database | Access Pattern | Why Not SQLite? |
|----------|---------------|----------------|
| **SQLite** | ACID CRUD (users, conversions) | — (it IS SQLite) |
| **Redis** | Atomic checkpoint save/load | SQLite lacks atomic crash-safe writes with sub-ms latency |
| **LanceDB** | Cosine similarity search on 768-dim vectors | SQLite has no native vector index |
| **DuckDB** | Columnar aggregations (AVG latency, GROUP BY model) | 10-100x faster than SQLite for analytics queries |

---

## 19. Knowledge Base System

### KB Entry Schema (LanceDB — 16 Fields)

| Field | Type | Purpose |
|-------|------|---------|
| `example_id` | string (UUID) | Unique identifier |
| `sas_code` | string | SAS source snippet |
| `python_code` | string | Python translation |
| `embedding` | float32[768] | Nomic text embedding vector |
| `partition_type` | string | SAS construct type |
| `complexity_tier` | string | LOW / MOD / HIGH |
| `target_runtime` | string | python / pyspark |
| `verified` | bool | Cross-verification passed |
| `source` | string | gold_standard / kb_gen / user_correction |
| `failure_mode` | string | Associated failure mode (if any) |
| `verification_method` | string | How verified |
| `verification_score` | float32 | Cross-verification confidence |
| `category` | string | 1 of 15 SAS categories |
| `version` | int32 | KB version (for rollback) |
| `superseded_by` | string | Newer version pointer |
| `created_at` | string (ISO) | Creation timestamp |

### KB Population Pipeline

```
 ┌───────────────────────────────────────────────────────────────────┐
 │  Knowledge Base Population Flow                                    │
 │                                                                   │
 │  Source 1: Gold Standard (45 pairs)                                │
 │  ┌─────────────────────────────┐                                  │
 │  │ Manually curated .sas +     │                                  │
 │  │ .gold.json annotation files │──────┐                           │
 │  │ gs_* (basic), gsm_* (med),  │      │                           │
 │  │ gsh_* (hard)                │      │                           │
 │  └─────────────────────────────┘      │                           │
 │                                       │                           │
 │  Source 2: Dual-LLM Generation         │                           │
 │  ┌─────────────────────────────┐      │                           │
 │  │ Prompt A → Azure: generate  │      │                           │
 │  │ Prompt B → Azure: translate │      │    ┌────────────────┐     │
 │  │ Prompt C → Groq: cross-     │──────┼───▶│   KBWriter      │     │
 │  │   verify (≥0.85 confidence) │      │    │   LanceDB       │     │
 │  └─────────────────────────────┘      │    │   IVF-64 index  │     │
 │                                       │    │   768-dim Nomic  │     │
 │  Source 3: User Corrections            │    └────────────────┘     │
 │  ┌─────────────────────────────┐      │                           │
 │  │ POST /api/conversions/      │      │                           │
 │  │   {id}/corrections          │──────┘                           │
 │  │ FeedbackIngestionAgent      │                                  │
 │  └─────────────────────────────┘                                  │
 │                                                                   │
 │  Coverage: 330 verified pairs across 15 SAS categories            │
 └───────────────────────────────────────────────────────────────────┘
```

---

## 20. Resilience Mechanisms

### Circuit Breaker State Machine

```
 ┌──────────────────────────────────────────────────────────────────┐
 │  CircuitBreaker State Machine                                     │
 │                                                                  │
 │      ┌──────────┐   N consecutive    ┌──────────┐               │
 │      │  CLOSED   │──── failures ────▶│   OPEN    │               │
 │      │ (normal)  │                   │(fail-fast)│               │
 │      └─────┬────┘                   └─────┬────┘               │
 │            │                               │                     │
 │      success                         timeout expires              │
 │            │                               │                     │
 │            │     ┌──────────┐              │                     │
 │            └────│HALF_OPEN │◄─────────────┘                     │
 │                  │(one probe)│                                    │
 │                  └─────┬────┘                                    │
 │                 success│ failure                                  │
 │                   ┌────┘└────┐                                   │
 │                   ▼          ▼                                    │
 │               CLOSED       OPEN                                  │
 │                                                                  │
 │  Azure: threshold=5 failures, reset=60s                          │
 │  Groq:  threshold=3 failures, reset=120s                         │
 └──────────────────────────────────────────────────────────────────┘
```

### Rate Limiter Configuration

| Provider | Max Concurrent | Reason |
|----------|---------------|--------|
| Azure OpenAI | 10 | Student tier ~60 RPM |
| Groq | 3 | Free tier 30 RPM (leave headroom) |

### Complete Resilience Table

| Mechanism | Implementation | File | Trigger | Effect |
|-----------|---------------|------|---------|--------|
| LLM Fallback Chain | Strategy Pattern | `llm_clients.py` | Provider failure | Next provider |
| Circuit Breaker | 3-state FSM | `retry.py` | N consecutive failures | Fail-fast |
| Rate Limiter | async Semaphore | `retry.py` | Concurrent call limit | Queue excess |
| Exponential Backoff | Decorator | `base_agent.py` | Transient failure | 1s→2s→4s delay |
| Groq Key Pool | Round-robin | `llm_clients.py` | 429 rate limit | Next API key |
| Redis Degraded | Flag check | `checkpoint.py` | Redis unavailable | No-op |
| Error Isolation | try/except per node | `orchestrator.py` | Node exception | Append to errors |
| Memory Monitor | psutil RSS | `large_file.py` | High memory | Limit threads |
| Partition Timeout | asyncio.wait_for | `translation_pipeline.py` | 120s exceeded | PARTIAL status |
| Stagnation Detection | Code comparison | `translation_pipeline.py` | 2 identical retries | Stop retrying |

---

## 21. Authentication & Security

### JWT Authentication Flow

```
 ┌──────────────────────────────────────────────────────────────┐
 │  JWT Flow                                                     │
 │                                                              │
 │  Login: POST /api/auth/login                                  │
 │  ┌──────────────────────────────────────────────────┐        │
 │  │ 1. Receive email + password                      │        │
 │  │ 2. Query UserRow by email                        │        │
 │  │ 3. bcrypt.verify(password, hashed_password)      │        │
 │  │    └── 12 rounds of salted hashing                │        │
 │  │ 4. create_access_token({sub: id, email, role})   │        │
 │  │    └── HS256 algorithm, 24-hour expiry            │        │
 │  │    └── Secret: CODARA_JWT_SECRET env var          │        │
 │  │ 5. Return { token, user }                         │        │
 │  └──────────────────────────────────────────────────┘        │
 │                                                              │
 │  Protected Endpoint:                                          │
 │  ┌──────────────────────────────────────────────────┐        │
 │  │ 1. Read Authorization: Bearer <token>             │        │
 │  │ 2. jwt.decode(token, secret, algorithms=["HS256"])│        │
 │  │ 3. Check expiry (24h)                             │        │
 │  │ 4. Extract {sub, email, role} → current_user      │        │
 │  │ 5. Proceed with request                           │        │
 │  └──────────────────────────────────────────────────┘        │
 │                                                              │
 │  GitHub OAuth:                                                │
 │  ┌──────────────────────────────────────────────────┐        │
 │  │ 1. Frontend → github.com/login/oauth/authorize    │        │
 │  │ 2. GitHub redirects with authorization code       │        │
 │  │ 3. Backend exchanges code for access token        │        │
 │  │ 4. Fetch GitHub profile + primary email           │        │
 │  │ 5. Create/link account, return JWT                │        │
 │  └──────────────────────────────────────────────────┘        │
 └──────────────────────────────────────────────────────────────┘
```

### Secret Management Architecture

```
 ┌──────────────────────────────────────────────────────────────┐
 │  Secret Loading Order                                         │
 │                                                              │
 │  Step 1: .env file (local dev / Docker)                       │
 │  ┌──────────────────────────────────────────────────┐        │
 │  │ python-dotenv: load_dotenv(".env", override=False)│        │
 │  └──────────────────────────────────────────────────┘        │
 │                                                              │
 │  Step 2: Azure Key Vault (production / staging)               │
 │  ┌──────────────────────────────────────────────────┐        │
 │  │ IF AZURE_KEYVAULT_URL is set:                     │        │
 │  │   DefaultAzureCredential → SecretClient           │        │
 │  │   Pull secrets into os.environ:                   │        │
 │  │     GROQ-API-KEY      → GROQ_API_KEY              │        │
 │  │     GROQ-API-KEY-2    → GROQ_API_KEY_2            │        │
 │  │     GROQ-API-KEY-3    → GROQ_API_KEY_3            │        │
 │  │     OLLAMA-API-KEY    → OLLAMA_API_KEY             │        │
 │  │     CODARA-JWT-SECRET → CODARA_JWT_SECRET          │        │
 │  │     GITHUB-CLIENT-SECRET → GITHUB_CLIENT_SECRET    │        │
 │  │   Falls back silently for missing secrets          │        │
 │  └──────────────────────────────────────────────────┘        │
 │                                                              │
 │  Step 3: Pydantic Settings                                    │
 │  ┌──────────────────────────────────────────────────┐        │
 │  │ Settings(BaseSettings) reads final env state      │        │
 │  │ All fields have defaults for local dev             │        │
 │  └──────────────────────────────────────────────────┘        │
 └──────────────────────────────────────────────────────────────┘
```

---

## 22. Frontend

### Component Architecture

```
 ┌────────────────────────────────────────────────────────────────┐
 │  Frontend Architecture (React 18 + TypeScript)                  │
 │                                                                │
 │  ┌──────────────────────────────────────────────────────┐      │
 │  │                     App.tsx                           │      │
 │  │  React Router v6 → route matching                    │      │
 │  └───────────┬──────────────┬──────────────┬────────────┘      │
 │              │              │              │                    │
 │      ┌───────▼──────┐ ┌────▼───────┐ ┌────▼──────────┐        │
 │      │  Login.tsx    │ │Workspace.tsx│ │ Dashboard.tsx │        │
 │      │  Signup.tsx   │ │            │ │              │        │
 │      │              │ │ Upload zone │ │ History      │        │
 │      │ GitHub OAuth │ │ Progress   │ │ Stats        │        │
 │      │              │ │ Diff view  │ │ Activity     │        │
 │      │              │ │ Download   │ │              │        │
 │      │              │ │ Correction │ │              │        │
 │      └──────────────┘ └────────────┘ └──────────────┘        │
 │              │                                                  │
 │      ┌───────▼──────────────────────────────────────────┐      │
 │      │           admin/ (role=admin only)                │      │
 │      │  Users.tsx | KBManagement.tsx | AuditLogs.tsx     │      │
 │      │  SystemHealth.tsx | PipelineConfig.tsx            │      │
 │      │  FileRegistry.tsx | KBChangelog.tsx               │      │
 │      └──────────────────────────────────────────────────┘      │
 │                                                                │
 │  State Management (Zustand stores):                             │
 │  ┌──────────────────────────────────────────────────────┐      │
 │  │ conversion-store.ts  │ user-store.ts │ theme-store.ts│      │
 │  │                      │               │               │      │
 │  │ upload()             │ login()       │ toggle()      │      │
 │  │ start()              │ signup()      │ dark/light    │      │
 │  │ startPolling(1.2s)   │ logout()      │               │      │
 │  │ stopPolling()        │ token mgmt    │               │      │
 │  └──────────────────────┴───────────────┴───────────────┘      │
 │                                                                │
 │  API Client (lib/api.ts):                                       │
 │  ┌──────────────────────────────────────────────────────┐      │
 │  │ fetch wrapper:                                       │      │
 │  │   Prepend /api to all paths                          │      │
 │  │   Attach Authorization: Bearer <token>                │      │
 │  │   Handle 401 → redirect to login                     │      │
 │  └──────────────────────────────────────────────────────┘      │
 │                                                                │
 │  UI Components: 57 shadcn/ui components                         │
 │  (Button, Card, Dialog, Table, Badge, Progress, Toast, ...)     │
 └────────────────────────────────────────────────────────────────┘
```

---

## 23. CI/CD Pipeline

### GitHub Actions — 6-Job Pipeline

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │  .github/workflows/ci.yml                                            │
 │  Triggers: push to main, PR to main (ignores docs/planning/md/tex)   │
 │                                                                      │
 │  ┌────────────┐                                                      │
 │  │  Job 1:     │                                                      │
 │  │  Lint &     │  ubuntu-latest, 5min timeout                         │
 │  │  Format     │  ruff check + black --check (line-length 100)        │
 │  └──────┬─────┘                                                      │
 │         │                                                            │
 │    ┌────┴────┐                                                       │
 │    ▼         ▼                                                       │
 │  ┌────────┐ ┌────────────┐                                           │
 │  │ Job 2:  │ │  Job 3:     │                                           │
 │  │ Tests & │ │  Security   │  Both depend on lint passing              │
 │  │Coverage │ │  Scan       │                                           │
 │  │         │ │             │                                           │
 │  │ 25min   │ │  10min      │                                           │
 │  │ Redis   │ │  safety     │                                           │
 │  │ service │ │  check      │                                           │
 │  │ pytest  │ │  (non-block)│                                           │
 │  │ codecov │ │             │                                           │
 │  └────┬───┘ └──────┬─────┘                                           │
 │       │             │                                                 │
 │       └──────┬──────┘                                                 │
 │              ▼                                                        │
 │  ┌──────────────────┐                                                 │
 │  │  Job 4: Docker    │  20min timeout                                  │
 │  │  Build & Push     │  Docker Buildx → ghcr.io                        │
 │  │                  │  Tags: branch, PR#, SHA, latest                  │
 │  │                  │  Only pushes on main branch                      │
 │  └────────┬─────────┘                                                 │
 │           │                                                           │
 │           ▼                                                           │
 │  ┌──────────────────┐                                                 │
 │  │  Job 5: Deploy    │  Azure OIDC (no stored credentials)             │
 │  │  to Azure         │  Update ca-codara-backend container              │
 │  │                  │  Smoke test: poll /api/health for 60s             │
 │  └────────┬─────────┘                                                 │
 │           │                                                           │
 │           ▼                                                           │
 │  ┌──────────────────┐                                                 │
 │  │  Job 6: Gold      │  Run benchmark against gold corpus               │
 │  │  Benchmark        │  Ensure no quality regression                     │
 │  └──────────────────┘                                                 │
 └──────────────────────────────────────────────────────────────────────┘
```

---

## 24. Docker & Azure Infrastructure

### Docker Multi-Stage Build

```
 ┌──────────────────────────────────────────────────────────────┐
 │  infra/Dockerfile                                             │
 │                                                              │
 │  Stage 1: builder (python:3.11-slim)                          │
 │  ┌──────────────────────────────────────────────────┐        │
 │  │ apt-get install gcc g++  (for torch/numpy/pyarrow)│        │
 │  │ pip install --prefix=/install -r requirements.txt │        │
 │  │ Result: pre-built packages in /install            │        │
 │  └──────────────────────────────────────────────────┘        │
 │                                                              │
 │  Stage 2: runtime (python:3.11-slim)                          │
 │  ┌──────────────────────────────────────────────────┐        │
 │  │ COPY --from=builder /install /usr/local           │        │
 │  │ COPY backend/ ./backend/                          │        │
 │  │ mkdir output logs lancedb_data backend/uploads     │        │
 │  │ adduser --system appuser (non-root)               │        │
 │  │ EXPOSE 8000                                       │        │
 │  │ CMD uvicorn api.main:app --host 0.0.0.0           │        │
 │  └──────────────────────────────────────────────────┘        │
 └──────────────────────────────────────────────────────────────┘
```

### Docker Compose (3 Services)

```
 ┌──────────────────────────────────────────────────────────────┐
 │  docker-compose.yml                                           │
 │                                                              │
 │  ┌──────────┐     ┌──────────────┐     ┌──────────────┐     │
 │  │  redis    │     │   backend     │     │   frontend    │     │
 │  │          │     │              │     │              │     │
 │  │ redis:7  │◄───│  port 8000   │     │  port 8080   │     │
 │  │ -alpine  │     │  depends_on: │     │  nginx       │     │
 │  │          │     │    redis     │     │  Vite build  │     │
 │  │ health:  │     │              │     │              │     │
 │  │ redis-cli│     │  Dockerfile  │     │  frontend/   │     │
 │  │ ping     │     │  (infra/)    │     │  Dockerfile  │     │
 │  └──────────┘     └──────────────┘     └──────────────┘     │
 └──────────────────────────────────────────────────────────────┘
```

### Azure Infrastructure (azure_setup.sh)

```
 ┌──────────────────────────────────────────────────────────────────┐
 │  Azure Resources Created                                          │
 │                                                                  │
 │  1. Resource Group: rg-codara                                     │
 │     └── Logical container for all resources                       │
 │                                                                  │
 │  2. Application Insights: ai-codara                               │
 │     └── Monitoring + telemetry (free tier)                        │
 │                                                                  │
 │  3. Key Vault: kv-codara                                          │
 │     └── 10 secrets with RBAC access control                       │
 │                                                                  │
 │  4. Managed Identity: id-codara-ci                                │
 │     └── Used by GitHub Actions (OIDC) + container app             │
 │                                                                  │
 │  5. Federated Credential                                          │
 │     └── Links managed identity ↔ GitHub repo (tass25/Stage)       │
 │                                                                  │
 │  6. Container Apps Environment: cae-codara                        │
 │     └── Serverless container hosting                              │
 │                                                                  │
 │  7. Container App: ca-codara-backend                              │
 │     ├── Key Vault secret references (runtime)                     │
 │     ├── External HTTPS ingress                                    │
 │     ├── Scale: 0 min → 2 max replicas                             │
 │     └── Resources: 0.5 CPU, 1GB RAM                               │
 │                                                                  │
 │  GitHub Secrets needed (3 only):                                   │
 │     AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID       │
 │  All actual API keys live in Key Vault                             │
 └──────────────────────────────────────────────────────────────────┘
```

---

## 25. Evaluation & Benchmarking

### Ablation Study Results

| Condition | hit-rate@5 | MRR | Translation Accuracy |
|-----------|-----------|-----|---------------------|
| flat_index (no clustering) | 0.71 | 0.54 | 82.2% |
| raptor_euclidean (GMM) | 0.84 | 0.63 | 82.2% |
| raptor_hyperbolic (Poincare) | 0.89 | 0.69 | 82.2% |
| finetune_7b + flat | 0.71 | 0.54 | 86.1% |
| **finetune_7b + hyper** | **0.89** | **0.69** | **87.4%** |

---

## 26. Gold Standard Corpus (50 Files, 721 Blocks)

The Gold Standard is the annotated reference corpus used for all evaluation, benchmarking, and boundary accuracy testing. It was manually created and annotated over Weeks 1-2.

### Tier Breakdown

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │                    GOLD STANDARD CORPUS STRUCTURE                     │
 │                                                                      │
 │  ┌────────────────────────────────────────────────────────────┐      │
 │  │  SIMPLE TIER (gs_*)                                         │      │
 │  │  15 files · ~350 blocks · 7-50 lines each                   │      │
 │  │  Single block type, minimal nesting, clean boundaries        │      │
 │  │                                                             │      │
 │  │  Files: gs_01_basic_data_step, gs_02_retain_accumulator,    │      │
 │  │  gs_03_merge_bygroup, gs_04_first_last, gs_05_etl_pipeline, │      │
 │  │  gs_07_multi_output, gs_08_hash_lookup, gs_11_proc_means,   │      │
 │  │  gs_12_proc_freq, gs_21_sql_simple, gs_22_sql_joins,        │      │
 │  │  gs_26_macro_basic, gs_37_do_loop_list, gs_42_include_refs, │      │
 │  │  gs_43_filename_libname                                     │      │
 │  └────────────────────────────────────────────────────────────┘      │
 │                                                                      │
 │  ┌────────────────────────────────────────────────────────────┐      │
 │  │  MEDIUM TIER (gsm_*)                                         │      │
 │  │  20 files · ~220 blocks · 100-250 lines each                 │      │
 │  │  Mixed types (3-6), macro calls, ETL workflows               │      │
 │  │                                                             │      │
 │  │  Files: financial_summary, customer_segmentation,            │      │
 │  │  claims_processing, inventory_analysis, employee_report,     │      │
 │  │  survey_analysis, time_series, data_cleaning, cohort_analysis│      │
 │  │  marketing_roi, risk_scoring, supply_chain, sales_dashboard, │      │
 │  │  compliance_check, ab_testing, data_reconciliation,          │      │
 │  │  etl_incremental, macro_reporting, longitudinal, audit_trail │      │
 │  └────────────────────────────────────────────────────────────┘      │
 │                                                                      │
 │  ┌────────────────────────────────────────────────────────────┐      │
 │  │  HARD TIER (gsh_*)                                           │      │
 │  │  15 files · ~151 blocks · 400+ lines each                    │      │
 │  │  Enterprise: nested macros, cross-file includes,             │      │
 │  │  CALL EXECUTE, circular dependencies                         │      │
 │  │                                                             │      │
 │  │  Files: enterprise_etl, macro_framework, warehouse_load,     │      │
 │  │  clinical_trial, fraud_detection, regulatory_report,         │      │
 │  │  migration_suite, batch_processor, analytics_pipeline,       │      │
 │  │  financial_recon, scoring_engine, data_governance,           │      │
 │  │  portfolio_analysis, multi_source_merge, complete_report     │      │
 │  └────────────────────────────────────────────────────────────┘      │
 └──────────────────────────────────────────────────────────────────────┘
```

### Annotation Format (`.gold.json`)

Each SAS file has a corresponding `.gold.json` that defines the ground truth:

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

### Block Type Distribution Across All 721 Blocks

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

### Boundary Accuracy Evaluation Algorithm

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │  Tolerance-Based Matching (TOLERANCE = 2 lines)                      │
 │                                                                      │
 │  For each gold block G and detected block D:                         │
 │                                                                      │
 │    is_match = (|D.line_start - G.line_start| <= 2)                   │
 │           AND (|D.line_end   - G.line_end|   <= 2)                   │
 │                                                                      │
 │  Result: 572 / 721 = 79.3% boundary accuracy                        │
 │                                                                      │
 │  Breakdown by tier:                                                  │
 │  ┌──────────┬─────────┬──────────┬──────────────┐                   │
 │  │ Tier     │ Blocks  │ Correct  │ Accuracy     │                   │
 │  ├──────────┼─────────┼──────────┼──────────────┤                   │
 │  │ Simple   │ ~350    │ ~310     │ ~88.6%       │                   │
 │  │ Medium   │ ~220    │ ~170     │ ~77.3%       │                   │
 │  │ Hard     │ ~151    │ ~92      │ ~60.9%       │                   │
 │  ├──────────┼─────────┼──────────┼──────────────┤                   │
 │  │ Total    │ 721     │ 572      │ 79.3%        │                   │
 │  └──────────┴─────────┴──────────┴──────────────┘                   │
 └──────────────────────────────────────────────────────────────────────┘
```

---

## 27. CDAIS — Formal Adversarial Testing (Deep Dive)

### The 6 Error Classes with Z3 Encoding

| ID | Name | Incidence | Applicability Regex | Witness Size | Synthesis Time |
|----|------|-----------|--------------------|----|------|
| C1 | `RETAIN_RESET` | 31.2% | `\bretain\b` + `\bby\b` | 6 rows (2G x 3R) | ~47ms |
| C2 | `LAG_QUEUE` | 8.4% | `\blag\s*\(` | 6 rows | ~35ms |
| C3 | `SORT_STABLE` | 4.7% | `\bproc\s+sort\b` | 6 rows | ~30ms |
| C4 | `NULL_ARITHMETIC` | 12.1% | `\bretain\b` + `\+` | 6 rows | ~40ms |
| C5 | `JOIN_TYPE` | 24.7% | `\bmerge\b` | 4+4 rows | ~45ms |
| C6 | `GROUP_BOUNDARY` | 18.9% | `\bfirst\.\w+\b` | 6 rows | ~35ms |

### RETAIN_RESET Encoding Detail

```
 ┌─────────────────────────────────────────────────────────────────┐
 │  Error Class: RETAIN_RESET (C1)                                  │
 │                                                                 │
 │  Setup: G=2 groups, R=3 rows per group                           │
 │  Symbolic: v[g][r] = z3.Int("v_g_r") for g∈{0,1}, r∈{0,1,2}    │
 │  Domain:   1 <= v[g][r] <= 100                                   │
 │                                                                 │
 │  Correct (per-group cumsum):                                     │
 │    C[0][0] = v[0][0]                                             │
 │    C[0][1] = v[0][0] + v[0][1]                                   │
 │    C[0][2] = v[0][0] + v[0][1] + v[0][2]                         │
 │    C[1][0] = v[1][0]                 ← RESETS here               │
 │    C[1][1] = v[1][0] + v[1][1]                                   │
 │    C[1][2] = v[1][0] + v[1][1] + v[1][2]                         │
 │                                                                 │
 │  Incorrect (global cumsum, no reset):                             │
 │    IC[0] = v[0][0]                                               │
 │    IC[1] = v[0][0] + v[0][1]                                     │
 │    IC[2] = v[0][0] + v[0][1] + v[0][2]                           │
 │    IC[3] = v[0][0] + v[0][1] + v[0][2] + v[1][0]  ← NO reset   │
 │    IC[4] = ... + v[1][1]                                         │
 │    IC[5] = ... + v[1][2]                                         │
 │                                                                 │
 │  Divergence: C[1][0] != IC[3]                                    │
 │    v[1][0] != v[0][0] + v[0][1] + v[0][2] + v[1][0]              │
 │    0 != v[0][0] + v[0][1] + v[0][2]                              │
 │    Always SAT since v[0][r] >= 1                                  │
 │                                                                 │
 │  Minimize: sum(all v[g][r]) → all values = 1                     │
 │                                                                 │
 │  Resulting Witness:                                               │
 │    group  value                                                   │
 │      A      1      correct cumsum: 1, 2, 3                       │
 │      A      1      incorrect:      1, 2, 3, 4, 5, 6              │
 │      A      1                                                     │
 │      B      1      ← divergence: correct=1, incorrect=4          │
 │      B      1                                                     │
 │      B      1                                                     │
 └─────────────────────────────────────────────────────────────────┘
```

### CDAIS Results

| Method | Detection Rate | False Positive | Witness Size | Synthesis Time |
|--------|---------------|---------------|-------------|---------------|
| Random testing (1K samples) | 72.4% | 2.1% | 1,000 rows | 0ms |
| Heuristic adversarial | 81.6% | 3.8% | 30 rows | 0ms |
| **CDAIS (Z3 synthesized)** | **94.3%** | **1.2%** | **6 rows** | **47ms** |
| CDAIS + Z3 repair loop | 96.8% | 1.2% | 6 rows | 89ms |

---

## 28. MIS — Migration Invariant Synthesis

### 18 Candidate Invariants

| Category | # | Invariant | Confirmed? |
|----------|---|-----------|------------|
| Structural | 1 | ROW_PRESERVATION_NON_FILTER | Yes (100% oracle, 94.7% translation) |
| | 2 | ROW_EQUALITY_SORT | Yes (100%, 95.5%) |
| | 3 | ROW_REDUCTION_AGGREGATION | Yes (100%, 88.9%) |
| | 4 | COLUMN_SUPERSET | Yes (100%, 92.7%) |
| | 5 | OUTPUT_NONEMPTY | Yes (100%, 97.8%) |
| | 6 | FIRST_LAST_SUBSET | Yes (100%, 84.2%) |
| | 7 | ROW_REDUCTION_DEDUP | Yes (100%, 88.9%) |
| Relational | 8 | SUM_PRESERVATION_NUMERIC | **No** (oracle fails) |
| | 9 | RETAIN_MONOTONE_CUMSUM | **No** (negative addends) |
| | 10 | FREQ_PERCENT_SUM_100 | Yes (100%, 91.7%) |
| | 11 | NO_NEGATIVE_COUNTS | Yes (100%, 95.8%) |
| | 12 | MERGE_OUTER_ROWCOUNT | **No** (edge cases) |
| | 13 | NO_DUPLICATE_GROUP_KEYS | **No** (edge cases) |
| Ordering | 14 | SORT_KEY_SORTED | Yes (100%, 86.4%) |
| Semantic | 15 | LAG_NULL_FIRST_ROW | **No** (BY-group config) |
| | 16 | GROUP_BOUNDARY_STRICT_SUBSET | Yes (100%, 78.6%) |
| | 17 | COLUMN_DTYPE_STABILITY | Yes (100%, 96.3%) |
| | 18 | MEANS_AGGREGATION_MONOTONE | Yes (100%, 94.4%) |

**12 of 18 confirmed** (66.7%). The 5 rejected had edge cases in oracle behavior.

---

## 29. HyperRAPTOR — Poincare Ball Clustering

### Why Hyperbolic Geometry for SAS Code?

SAS code has a deeply hierarchical structure that maps poorly to Euclidean space:

```
 SAS Code Hierarchy (inherently tree-shaped):
 ┌──────────────────────────────────────────────────────────────────┐
 │                                                                  │
 │  Macro library                                                   │
 │  ├── %macro_A                                                    │
 │  │   ├── PROC SQL (inner query)                                  │
 │  │   └── DATA step (post-process)                                │
 │  └── %macro_B                                                    │
 │      ├── PROC MEANS                                              │
 │      └── PROC REPORT                                             │
 │                                                                  │
 │  This is a TREE. Trees cannot be embedded without distortion     │
 │  in Euclidean space — you need exponentially growing dimensions   │
 │  to represent tree distance accurately (Sarkar, 2011).           │
 │                                                                  │
 │  In Euclidean space: a macro and its child PROC might end up     │
 │  in different clusters that look geometrically close but mean     │
 │  nothing semantically.                                           │
 └──────────────────────────────────────────────────────────────────┘
```

**Academic reference**: Nickel & Kiela, *"Poincare Embeddings for Learning Hierarchical Representations"*, NeurIPS 2017.

### Euclidean vs Hyperbolic Comparison

```
 Euclidean Space (flat):          Hyperbolic Space (Poincare ball):
 ┌────────────────────────┐      ┌─────────────────────────────┐
 │                        │      │         ○ root               │
 │  ○  ○  ○  ○  ○  ○     │      │      ╱    ╲                  │
 │                        │      │    ○        ○   clusters     │
 │  ○  ○  ○  ○  ○  ○     │      │   ╱╲      ╱╲                │
 │                        │      │  ○  ○    ○  ○  leaves        │
 │  All points equidistant│      │ ╱╲╱╲  ╱╲╱╲                  │
 │  No hierarchy encoded  │      │○○○○  ○○○○  at boundary      │
 │                        │      │                             │
 │  Parent-child distances│      │  Distances grow exponentially│
 │  get distorted         │      │  toward boundary — more room │
 │                        │      │  for leaf nodes              │
 └────────────────────────┘      └─────────────────────────────┘

 The Poincare ball is a unit ball where:
  - CENTER = "root" (high-level macro definitions, abstract)
  - BOUNDARY = "leaves" (specific DATA steps, PROC blocks, concrete)
  - Distance near boundary grows MUCH faster than near center

 This naturally matches SAS hierarchy:
  - Macro definitions cluster near center (abstract, shared)
  - Concrete DATA steps cluster near boundary (specific, leaf-level)
```

### HyperRAPTOR Algorithm (Step by Step)

```
 Step 1: Take 768-dim Nomic embeddings (Euclidean)
         │
         ▼
 Step 2: Project to Poincare ball via exponential map:
         x → tanh(‖x‖/2) · (x/‖x‖)
         (maps any real vector to a point strictly inside the unit ball)
         │
         ▼
 Step 3: Initialise K centroids via K-means++ on the ball
         │
         ▼
 Step 4: Iterate until convergence:
         - Assignment: nearest centroid (Poincare distance, not Euclidean)
         - Update: Frechet mean of members (Riemannian SGD on manifold)
         │
         ▼
 Step 5: Return cluster assignments
```

`geoopt` (Geometric Optimization in PyTorch) provides the `PoincareBall` manifold operations — parallel transport, exponential/logarithmic maps, Frechet means.

### Fallback Behavior

If `geoopt` is not installed, `HyperRAPTORClusterer.cluster()` logs a warning and **automatically falls back to `GMMClusterer`**. The pipeline never breaks. Enabled via `USE_HYPER_RAPTOR=true` in `.env`.

### Results

| Metric | Euclidean GMM | HyperRAPTOR | Delta |
|--------|--------------|-------------|-------|
| hit-rate@5 | 0.84 | 0.89 | +6.0% |
| MRR | 0.63 | 0.69 | +9.5% |
| MOD/HIGH advantage vs flat | +11% | +17% | +6pp |

---

## 30. QLoRA Fine-Tuning Pipeline

### Training Corpus Composition (1,200 Pairs)

| Source | Pairs | Method |
|--------|-------|--------|
| Internal gold standard | 45 | Manually curated |
| KB pairs (verified) | 330 | Dual-LLM generation |
| The Stack v2 (SAS files) | 390 | Auto-translated |
| GitHub API scrape (SAS repos) | 148 | Scraped + translated |
| Teacher LLM distillation | 212 | GLM-4-Flash + Gemini |
| Stack Overflow (SAS tag) | 75 | Extracted + translated |
| **Total (post-dedup)** | **1,200** | MinHash LSH (threshold 0.8) |

### Training Configuration

| Parameter | SFT | DPO |
|-----------|-----|-----|
| Base model | Qwen2.5-Coder-7B-Instruct | SFT checkpoint |
| Framework | unsloth + trl SFTTrainer | trl DPOTrainer |
| Quantization | 4-bit QLoRA (r=16, alpha=32, dropout=0.05) | Same |
| Platform | Lightning AI (2x A10G) | Same |
| Dataset | 1,100 train / 100 val | 87 correction pairs |
| Epochs | 3 | 1 |
| Final metric | Perplexity: 2.61, Loss: 0.34 | Reward margin: +0.23 |

### Integration in LLM Chain

```
 Tier 0 — LocalModelClient (GGUF Q4_K_M, ~4.5GB, CPU, ~200ms)
   │ Used for LOW risk only
   │ IF unavailable ↓
 Tier 1 — Ollama minimax-m2.7:cloud (PRIMARY, free, ~2s)
   │ IF unavailable ↓
 Tier 2 — Azure GPT-4o / GPT-4o-mini (enterprise SLA, ~3s)
   │ IF unavailable ↓
 Tier 3 — Groq LLaMA-3.3-70B (free tier, ~1s, + cross-verifier)
   │ IF unavailable ↓
 PARTIAL status (all exhausted)
```

---

## 31. The 6 Failure Modes (Detailed)

### Failure Mode Reference Table

| # | Mode | SAS Pattern | Common Mistranslation | Correct Python |
|---|------|-------------|----------------------|---------------|
| 1 | RETAIN | `RETAIN var 0; IF FIRST.grp THEN var=0; var+x;` | `df['var'] = df['x'].cumsum()` (global) | `df.groupby('grp')['x'].cumsum()` |
| 2 | FIRST_LAST | `IF FIRST.state;` | `df.head(1)` or `df.iloc[0]` | `df.groupby('state').first()` |
| 3 | DATE_ARITHMETIC | `today_sas = today();` | Python datetime (epoch 1970) | `pd.to_datetime(sas_date, origin='1960-01-01')` |
| 4 | MERGE_SEMANTICS | `MERGE left right; BY id;` | `pd.merge(how='inner')` (default) | `pd.merge(how='outer')` |
| 5 | MISSING_VALUE | `total = revenue + tax;` (tax=.) | `NaN + x = NaN` (propagation) | `df[['revenue','tax']].sum(axis=1)` |
| 6 | PROC_MEANS_OUTPUT | `PROC MEANS NWAY; OUTPUT OUT=...` | Missing `_TYPE_`, `_FREQ_` columns | Include count + ensure NWAY semantics |

---

## 32. KB Dual-LLM Generation Chain

### Generation Pipeline Schema

```
 ┌──────────────────────────────────────────────────────────────────┐
 │  generate_kb_pairs.py                                             │
 │                                                                  │
 │  For each (category, complexity_tier):                             │
 │                                                                  │
 │  ┌────────────────────────────────────────────────────────┐      │
 │  │ Prompt A → Azure GPT-4o                                │      │
 │  │ "Generate a realistic SAS code snippet for category    │      │
 │  │  DATA_STEP_RETAIN, complexity HIGH"                    │      │
 │  │                                                       │      │
 │  │ Output: GeneratedSAS (sas_code, category, tier,        │      │
 │  │         failure_mode, description)                     │      │
 │  └────────────────────────────────────────────────────────┘      │
 │                          │                                       │
 │                          ▼                                       │
 │  ┌────────────────────────────────────────────────────────┐      │
 │  │ Prompt B → Azure GPT-4o                                │      │
 │  │ "Convert this SAS code to Python (pandas)"             │      │
 │  │                                                       │      │
 │  │ Output: ConvertedPython (python_code, runtime,          │      │
 │  │         imports_needed, notes)                          │      │
 │  └────────────────────────────────────────────────────────┘      │
 │                          │                                       │
 │                          ▼                                       │
 │  ┌────────────────────────────────────────────────────────┐      │
 │  │ Prompt C → Groq LLaMA-3.1-70B (DIFFERENT provider)     │      │
 │  │ "Are these two code snippets semantically equivalent?"  │      │
 │  │                                                       │      │
 │  │ Output: CrossVerifyResult (equivalent, confidence,      │      │
 │  │         issues)                                         │      │
 │  │                                                       │      │
 │  │ Gate: equivalent=True AND confidence >= 0.85            │      │
 │  │ Reject rate: ~15% of generated pairs                    │      │
 │  └────────────────────────────────────────────────────────┘      │
 │                          │                                       │
 │                 IF passes gate                                    │
 │                          ▼                                       │
 │  ┌────────────────────────────────────────────────────────┐      │
 │  │ KBWriter → LanceDB                                     │      │
 │  │   embed(sas_code) → 768-dim vector (Nomic)             │      │
 │  │   Store 16-field record                                │      │
 │  │   Rebuild IVF-64 index if threshold reached            │      │
 │  └────────────────────────────────────────────────────────┘      │
 └──────────────────────────────────────────────────────────────────┘
```

### Coverage Matrix (15 Categories)

| Category | Target | Failure Mode | Current |
|----------|--------|-------------|---------|
| DATA_STEP_BASIC | 30 | — | 30 |
| DATA_STEP_MERGE | 25 | MERGE_SEMANTICS | 25 |
| DATA_STEP_RETAIN | 20 | RETAIN | 20 |
| DATA_STEP_ARRAY | 20 | — | 20 |
| DATA_STEP_FIRST_LAST | 25 | FIRST_LAST | 25 |
| DATE_ARITHMETIC | 30 | DATE_ARITHMETIC | 30 |
| PROC_SQL | 30 | — | 30 |
| PROC_MEANS | 20 | PROC_MEANS_OUTPUT | 20 |
| PROC_FREQ | 15 | — | 15 |
| MACRO_BASIC | 25 | — | 25 |
| MACRO_CONDITIONAL | 20 | — | 20 |
| PROC_SORT | 15 | — | 15 |
| PROC_REG_LOGISTIC | 20 | — | 20 |
| PROC_IMPORT_EXPORT | 15 | — | 15 |
| MISSING_VALUE_HANDLING | 20 | MISSING_VALUE | 20 |
| **Total** | **330** | 6 modes | **330** |

---

## 33. Azure Enterprise Architecture Rationale

### Why Cloud vs Local

The project started as a local prototype running everything on a laptop. This section explains the architectural shift to a hybrid local/cloud model — and why each decision was made.

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │  ARCHITECTURAL DECISION: LOCAL vs CLOUD                                  │
 │                                                                          │
 │  ┌──────────────────────────────┐  ┌────────────────────────────────┐   │
 │  │       KEEP LOCAL              │  │        MOVE TO CLOUD            │   │
 │  │                               │  │                                 │   │
 │  │  LanceDB (vector store)       │  │  LLM Inference → Azure OpenAI  │   │
 │  │    → no API latency for       │  │    → enterprise SLA, no 429s   │   │
 │  │      embedding search         │  │    → reserved capacity         │   │
 │  │                               │  │    → tiered routing saves $$    │   │
 │  │  Nomic Embed v1.5             │  │                                 │   │
 │  │    → free, local inference    │  │  Telemetry → Azure Monitor     │   │
 │  │    → no API cost              │  │    → live dashboards            │   │
 │  │                               │  │    → App Insights tracing       │   │
 │  │  File persistence (output/)   │  │    → directors read dashboards, │   │
 │  │    → simple, no network       │  │      not log files              │   │
 │  │                               │  │                                 │   │
 │  │  SQLite (partition data)      │  │  CI/CD → GitHub Actions         │   │
 │  │    → embedded, zero-config    │  │    → automated test/lint/scan   │   │
 │  │                               │  │    → CodeQL security analysis   │   │
 │  │  NetworkX (in-memory graph)   │  │                                 │   │
 │  │    → fast SCC traversal       │  │  Hosting → Azure Container Apps │   │
 │  │                               │  │    → serverless (scale to zero) │   │
 │  │                               │  │    → saves credits when idle    │   │
 │  │                               │  │                                 │   │
 │  │                               │  │  Secrets → Azure Key Vault      │   │
 │  │                               │  │    → zero secrets in code/env   │   │
 │  │                               │  │                                 │   │
 │  │                               │  │  Reports → Azure Static Web     │   │
 │  │                               │  │    → HTML reports for defense   │   │
 │  └──────────────────────────────┘  └────────────────────────────────┘   │
 └──────────────────────────────────────────────────────────────────────────┘
```

### The Groq Problem (Why Azure OpenAI Was Promoted)

Before Week 9, the primary LLM was Groq (free tier). This created a critical bottleneck:

```
 Groq free tier: 30 RPM (requests per minute)
 
 A 10,000-line SAS file produces ~200 partitions
 Each partition needs:
   1x translation call
   1x cross-verification call
   (+ potential retry calls)
 
 200 partitions × 2 calls = 400 LLM calls
 At 30 RPM → 400 / 30 = 13.3 minutes of RATE LIMIT WAITING
 
 Azure OpenAI with $100 student credit:
   GPT-4o-mini at $0.15/1M input tokens
   50-file corpus costs < $2 total
   No rate limit delays
   Enterprise SLA with predictable QoS
```

This is why `v2.0.0` (Week 9) promoted Azure OpenAI to primary and demoted Groq to fallback. The fallback chain became: **Ollama → Azure → Groq** (instead of Groq → Ollama).

### Cost Efficiency Through Tiered Routing

```
 ┌──────────────────────────────────────────────────────────────────┐
 │  LLM Cost Routing Strategy                                       │
 │                                                                  │
 │  Risk Level    │  Model              │  Cost           │  Usage  │
 │  ──────────────┼─────────────────────┼─────────────────┼──────── │
 │  LOW (60%)     │  Local GGUF / mini  │  $0 / $0.15/1M  │  ~60%  │
 │  MODERATE (25%)│  GPT-4o-mini        │  $0.15/1M input │  ~25%  │
 │  HIGH (15%)    │  GPT-4o full        │  $2.50/1M input │  ~15%  │
 │                │                     │                 │        │
 │  Estimated cost for 50-file corpus:  │  < $5 total     │        │
 │  Estimated cost for 10K-line file:   │  < $0.50        │        │
 └──────────────────────────────────────────────────────────────────┘
```

---

## 34. Code Quality & Audit Trail

### Independent Audit Process

The codebase went through 2 waves of independent audit in Week 13, resulting in 44+20 fixes:

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │                     AUDIT PROCESS (2 Waves)                          │
 │                                                                      │
 │  Wave 1 (44 issues):                                                 │
 │  ┌────────────────────────────────────────────────────────────┐      │
 │  │ Initial audit found 44 issues:                              │      │
 │  │  - Pipeline stages 2-5 had placeholder implementations      │      │
 │  │  - Hardcoded default passwords in api/main.py               │      │
 │  │  - No rate limiting on auth endpoints                        │      │
 │  │  - No file size/MIME validation on uploads                   │      │
 │  │  - Duplicate _translate_azure_* methods                      │      │
 │  │  - asyncio.to_thread without timeout guards on LLM calls     │      │
 │  │  - conv.accuracy hardcoded to 100.0                          │      │
 │  │  - Unused imports throughout translation_agent.py            │      │
 │  │  - Dead code in orchestrator and llm_clients                 │      │
 │  │  ALL 44 FIXED                                               │      │
 │  └────────────────────────────────────────────────────────────┘      │
 │                                                                      │
 │  Wave 2 (20 issues — consolidation):                                 │
 │  ┌────────────────────────────────────────────────────────────┐      │
 │  │ Structural cleanup:                                         │      │
 │  │  - api/auth.py, api/database.py, api/schemas.py deleted     │      │
 │  │    (pure re-export shims → direct imports)                   │      │
 │  │  - streaming/backpressure.py inlined into pipeline.py        │      │
 │  │  - raptor_node.py merged into partition_ir.py                │      │
 │  │  - logging_config.py moved to partition/utils/               │      │
 │  │  - __all__ exports added to all __init__.py files            │      │
 │  │  ALL 20 FIXED                                               │      │
 │  └────────────────────────────────────────────────────────────┘      │
 │                                                                      │
 │  Final Audit Grade: B+ (upgraded from C+ baseline)                   │
 └──────────────────────────────────────────────────────────────────────┘
```

### Key Fixes Table

| Severity | Issue | Fix Applied |
|----------|-------|-------------|
| HIGH | Pipeline stages 2-5 had `time.sleep()` stubs | All stages now call real agents |
| HIGH | Hardcoded passwords in `api/main.py` | `secrets.token_urlsafe(18)` + env var |
| HIGH | No rate limiting on login/signup | `_check_rate_limit()`: 5 req/IP/60s, HTTP 429 |
| HIGH | `_cross_verify` lacked `asyncio.wait_for` | All LLM calls now timeout-guarded |
| HIGH | `conv.accuracy = 100.0` hardcoded | Derived from `translation_ok + syntax_ok` |
| MEDIUM | No file size limit on uploads | 50 MB enforced before write |
| MEDIUM | No MIME validation on uploads | `_ALLOWED_CONTENT_TYPES` frozenset |
| MEDIUM | Z3 not wired into TranslationPipeline | Z3 + CEGAR repair loop added |
| MEDIUM | `TranslationPipeline` no DI | Three optional constructor params |
| LOW | Duplicate `_translate_azure_*` methods | Merged into `_translate_with_model()` |
| LOW | Dead code in orchestrator + llm_clients | All removed |
| LOW | Unused imports (os, datetime, etc.) | All removed |

### Remaining Issues (Post-Audit)

| Severity | Issue | Status |
|----------|-------|--------|
| MEDIUM | Zero API route test coverage | Open — no `test_api_*.py` files exist |
| LOW | `process()` in TranslationAgent is 142 lines | Functional, refactor candidate |
| LOW | `confidence=0.80` magic number | Low priority cosmetic |

### Build Verification

All files pass `py_compile` syntax check: `api/main.py`, `api/routes/auth.py`, `api/routes/conversions.py`, `api/services/pipeline_service.py`, `partition/translation/translation_agent.py`, `partition/translation/translation_pipeline.py`, `partition/orchestration/orchestrator.py`, `partition/models/partition_ir.py`, `partition/streaming/pipeline.py`, and all `__init__.py` files.

---

## 35. Version History (CHANGELOG)

### v3.1.0 — 2026-04-12

**Added:**
- `backend/api/services/` layer: `ConversionService`, `PipelineService`, `TranslationService` — extracted from the 1063-line `routes/conversions.py`
- `backend/config/constants.py` — named constants replacing magic numbers (`AZURE_MAX_COMPLETION_TOKENS`, `GROQ_MAX_TOKENS`, `SSE_MAX_EVENTS`)
- `cors_origins` field in `config.settings.Settings` — CORS configurable via env var

**Changed:**
- All `os.getenv()` calls migrated to `config.settings`
- All route files import from `api.core.*` instead of shim files
- `_run_pipeline_sync` (239 lines) moved to `pipeline_service.py`
- `_translate_sas_to_python` (154 lines) moved to `translation_service.py`
- `conversions.py` reduced from **1063 lines → ~310 lines** (route handlers only)

**Fixed:**
- Unused `import shutil` removed
- Duplicate import deduplicated
- `DB_PATH` module-level variable replaced with `settings.sqlite_path`

### v3.0.0 — 2026-04-06 (Week 13 Restructure)

- 11-node orchestrator reduced to **8 composite nodes** (facade pattern)
- Full repo reorganization into logical subfolders
- 44+20 audit fixes (Audit grade: B+, upgraded from C+)
- Azure Monitor telemetry, GitHub Actions CI/CD, CodeQL, Docker

### v2.0.0 — 2026-03-15 (Week 9)

- Azure OpenAI promoted to **primary LLM** (replaced Ollama/Groq-primary)
- `RateLimitSemaphore`, `CircuitBreaker` added (resilience layer)
- `KBWriter` (LanceDB, 330 pairs), dual-LLM generation pipeline

### v1.0.0 — 2026-02-01 (Weeks 1-2)

- Initial `FileAnalysisAgent`, `CrossFileDepsResolver`, `RegistryWriterAgent`
- Gold standard corpus: 50 files, 721 blocks
- SQLite + structlog + Pydantic v2 foundation

---

## 36. Week-by-Week Build History

| Week | Phase | Key Deliverables | Tests | Key Decision |
|------|-------|-----------------|-------|-------------|
| 1-2 | L2-A (Foundation) | FileAnalysisAgent, CrossFileDepsResolver, RegistryWriter, DataLineageExtractor, SQLite, Gold corpus (50 files, 721 blocks) | 20 | BaseAgent ABC, Pydantic v2, structlog |
| 2-3 | L2-B (Streaming) | StreamAgent, StateAgent FSM (17 regex patterns), asyncio.Queue with backpressure | 27 | Producer/consumer pattern |
| 3-4 | L2-C (Chunking) | BoundaryDetector (deterministic 80% + LLM 20%), PartitionBuilder | ~60 | Hybrid detection strategy |
| 4 | L2-D (Complexity) | ComplexityAgent (LogReg + Platt, ECE=0.06), StrategyAgent, 14 features | ~80 | ML-calibrated scoring |
| 5-6 | RAPTOR | NomicEmbedder (768d), GMMClusterer (tau=0.72), ClusterSummarizer, RAPTORTreeBuilder | ~100 | Soft assignment (GMM > K-means) |
| 7 | L2-E (Persistence) | PersistenceAgent, IndexAgent, NetworkX SCC (Tarjan), DuckDB 3-table schema | 115 | Tarjan's algorithm for circular deps |
| 8 | Orchestrator | PartitionOrchestrator (LangGraph StateGraph), RedisCheckpointManager, LLMAuditLogger | 126 | LangGraph over LangChain |
| 9 | Resilience + KB | RateLimitSemaphore, CircuitBreaker, MemoryMonitor, KBWriter (LanceDB IVF-64), kb_changelog, generate_kb_pairs.py (dual-LLM), 330 KB pairs | 144 | Azure promoted to primary LLM |
| 10 | L3 (Translation) | TranslationAgent (3-tier RAG), ValidationAgent (subprocess sandbox), TranslationPipeline (retry + cross-verify), full LLM fallback chain | 169 | Subprocess sandbox (.kill() not .join()) |
| 11 | L4 (Merge) | ImportConsolidator, DependencyInjector, ScriptMerger, ReportAgent, FeedbackIngestion, QualityMonitor, RetrainTrigger | 191 | PEP 8 import ordering |
| 12 | Evaluation | Ablation study infrastructure (flat_index, query_generator, ablation_runner), DuckDB schema | 198 | RAPTOR +18.3% hit-rate vs flat |
| 13 | v3.0.0 Enterprise | 11→8 nodes (facade pattern), 44+20 audit fixes, Azure OpenTelemetry, GitHub Actions CI (6 jobs), Docker multi-stage, CodeQL | 221 | Facade pattern consolidation |
| 14 | Buffer | Defense preparation, documentation | 221 | — |
| 15+ | v3.1.0 Research | Z3 (11 patterns), HyperRAPTOR (+6% hit-rate), QLoRA Qwen2.5-7B (1200 pairs, perplexity 2.61), CDAIS + MIS, Ollama minimax promoted to primary | 248+ | 5-tier LLM chain |

### Bugs Encountered & Lessons Learned

These are the actual bugs found during development and how they shaped the architecture:

| Week | Bug | Root Cause | Fix | Lesson |
|------|-----|-----------|-----|--------|
| 1-2 | SHA-256 hash mismatch across OS | Windows `write_text` uses `\r\n`, Linux uses `\n` | Hash from `read_bytes()` (raw bytes) | Always hash raw bytes, not decoded text |
| 1-2 | Cross-file dep test failures | Target file must be in `files` list for resolver to build index | Pass both source and target files | Integration tests need realistic inputs |
| 1-2 | `chardet` encoding detection variance | `chardet` reports `ISO-8859-1` or `Windows-1252` for same content | Tests accept both encodings | Don't test for exact encoding strings |
| 2-3 | Regex `\b%DO\b` never matched | `\b` before `%` fails — both sides are non-word chars | Changed to `%DO\b` (no leading `\b`) | SAS macros break standard regex word boundaries |
| 2-3 | Shallow copy shared mutable lists | `model_copy()` shared nested lists across snapshots | `model_copy(deep=True)` | Pydantic models need deep copies for mutation |
| 2-3 | Streaming benchmark flaky at 2.0s | Initial FSM wasn't optimized yet | Raised threshold to 5.0s (perf sprint planned for later) | Set realistic initial benchmarks |
| 10 | Sandbox process hangs on Windows | `.join()` blocks if child deadlocks | `.kill()` + timeout guard | Never `.join()` untrusted subprocess — always `.kill()` |
| 13 | `conv.accuracy` always 100% | Hardcoded `100.0` instead of computing from results | Derived from `translation_ok + syntax_ok` flags | Never hardcode evaluation metrics |
| 13 | No timeout on LLM calls | `asyncio.to_thread` without `asyncio.wait_for` | Added timeout guards on all 3 LLM call sites | Every external call needs a timeout |

### Week-by-Week Performance Metrics

| Week | Metric | Target | Actual |
|------|--------|--------|--------|
| 2-3 | Streaming throughput (10K lines) | < 5s | ~2.8s |
| 2-3 | Peak memory (10K lines) | ≤ 100 MB | < 10 MB |
| 2-3 | FSM block_type accuracy | ≥ 0.95 | 1.00 (4/4) |
| 4 | ECE (calibration error) | < 0.08 | 0.06 |
| 5-6 | RAPTOR hit-rate@5 | ≥ 0.82 | 0.9638 |
| 5-6 | RAPTOR MRR | ≥ 0.60 | 0.9427 |
| 12 | RAPTOR vs flat improvement | > +10% | +18.3% |
| 13 | Audit grade | ≥ B | B+ (from C+) |
| 13 | Tests passing | > 95% | 97.7% (216/221) |
| 15+ | Z3 provability (LOW risk) | > 30% | ~41% |
| 15+ | CDAIS detection rate | > 90% | 94.3% |

---

## 37. File-by-File Reference

### Configuration Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Python project config, pytest settings |
| `backend/config/settings.py` | Pydantic Settings: all env vars with defaults |
| `backend/config/constants.py` | Global constants (max file size, extensions) |
| `backend/config/project_config.yaml` | Runtime pipeline configuration |

### Prompt Templates (`backend/partition/prompts/`)

| Template | Used By | Purpose |
|----------|---------|---------|
| `translation_static.j2` | Static RAG | Simple translation with KB examples |
| `translation_graph.j2` | GraphRAG | Translation with dependency context |
| `translation_agentic.j2` | Agentic RAG | Complex translation with reflection |
| `cross_verify.j2` | TranslationAgent | Independent verification (Prompt C) |
| `reflection.j2` | TranslationAgent | Self-reflection for retry |
| `entity_extraction.j2` | RAPTOR | Entity extraction for clustering |

### Test Files (248+ tests)

| Test File | Coverage |
|-----------|----------|
| `test_streaming.py` | StreamAgent, StateAgent FSM |
| `test_boundary_detector.py` | BoundaryDetector + LLM resolver |
| `test_complexity_agent.py` | ComplexityAgent ML + rule fallback |
| `test_strategy_agent.py` | StrategyAgent routing logic |
| `test_rag.py` | RAGRouter, all 3 paradigms |
| `test_raptor.py` | RAPTOR tree building |
| `test_translation.py` | TranslationAgent, cross-verify |
| `test_orchestration.py` | Full pipeline integration |
| `test_persistence.py` | SQLite persistence |
| `test_evaluation.py` | Flat index + ablation queries |
| `test_merge_retraining.py` | MergeAgent + KB feedback loop |
| `test_z3_verification.py` | Z3 formal verification patterns |
| `test_z3_effect.py` | Z3 effect on quality |
| `test_cdais.py` | CDAIS adversarial testing |
| `test_critical_paths.py` | Critical path coverage |
| `test_local_model_client.py` | Local GGUF model loading |
| `test_regression.py` | Regression detection |
| `regression/test_ablation.py` | RAPTOR vs flat ablation |

### Operational Scripts

| Script | Purpose |
|--------|---------|
| `scripts/ops/run_pipeline.py` | CLI: run pipeline on a SAS file |
| `scripts/ops/submit_correction.py` | Submit correction to KB from CLI |
| `scripts/ops/verify_deliverables.py` | Check all deliverables exist |
| `scripts/ops/view_db_html.py` | Inspect database contents as HTML |
| `scripts/kb/generate_kb_pairs.py` | Dual-LLM KB pair generation |
| `scripts/kb/expand_kb.py` | Batch KB expansion |
| `scripts/kb/kb_rollback.py` | Rollback KB to previous version |
| `scripts/kb/build_dataset.py` | Multi-source fine-tuning dataset |
| `scripts/eval/translate_test.py` | End-to-end translation test |
| `scripts/eval/run_benchmark.py` | Full benchmark suite |

---

## Summary of Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **LangGraph over LangChain** | Explicit state machines, deterministic execution, per-node checkpointing |
| **3 LLM providers (now 6)** | Resilience (fallback chain) + accuracy (cross-verification on different provider) |
| **4 databases** | Each optimized for its access pattern: ACID (SQLite), crash recovery (Redis), vector search (LanceDB), analytics (DuckDB) |
| **Z3 formal verification** | Mathematical proof of correctness, not just testing |
| **CDAIS adversarial testing** | Z3-synthesized minimal witnesses that expose 94.3% of semantic errors |
| **MIS invariants** | Corpus-derived properties catch 87.5% of errors not caught by execution |
| **RAPTOR clustering** | Hierarchical retrieval outperforms flat search (+18.3% hit-rate@5) |
| **3 RAG paradigms** | Right-sized retrieval: simple blocks don't need graph traversal |
| **Subprocess sandbox** | True process isolation via `multiprocessing.Process + .kill()` |
| **Strategy Pattern (LLM)** | Clean fallback chain with independent circuit breakers per provider |
| **Azure Key Vault + OIDC** | Zero stored credentials in code, CI, or env vars |
| **Docker multi-stage build** | Separates build tools from runtime for smaller images |
| **Facade pattern (8 nodes)** | Orchestrator sees 8 clean nodes; complexity is internal to each facade |
| **QLoRA fine-tuning** | Domain-specific 7B model runs locally (Tier 0), zero API cost for LOW risk |
| **Dual-LLM KB generation** | Different provider verifies (Groq) than generates (Azure) → catches 15% errors |
