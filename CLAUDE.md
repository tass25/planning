# CLAUDE.md — Codara Project Memory
<!-- Optimized for AI ingestion. Last updated: 2026-03-24 -->

## PROJECT IDENTITY
**Name**: Codara — SAS→Python/PySpark Conversion Accelerator
**Type**: PFE (internship/thesis) project, ~14-week sprint
**Stage**: Week 13-14 (final polish, near-complete)
**Version**: 3.0.0 (pipeline restructured to 8 orchestrator nodes in Week 13; each node backed by 1–4 specialist sub-agents)
**Old package name**: `sas_converter/` (renamed to `backend/` — CI was fixed in Week 13)
**Audit grade**: A- (after 44 fixes across 4 rounds + 20 post-audit fixes)

---

## ARCHITECTURE OVERVIEW

Three-tier stack:
```
Frontend (React/Vite :5173) ──/api proxy──► Backend (FastAPI :8000) ──► Pipeline (LangGraph)
                                                     │
                                             SQLite (API DB)
                                             Redis (checkpoints)
                                             LanceDB (KB embeddings)
                                             DuckDB (LLM audit logs)
```

### 8-Node LangGraph Pipeline (linear, async)
```
file_process → streaming → chunking → raptor → risk_routing → persist_index → translation → merge → END
     L2-A         L2-B       L2-C      L2-C       L2-D            L2-E             L3          L4
```

**Layers**:
- L2-A: File scan, registry, cross-file dep resolution
- L2-B: Streaming parser (FSM-based, producer/consumer queue)
- L2-C: Boundary detection (deterministic + LLM fallback) + RAPTOR clustering
- L2-D: Complexity scoring (ML calibrated) + strategy assignment
- L2-E: SQLite persistence + NetworkX dependency graph/SCC indexing
- L3: Translation (3-tier RAG: Static/GraphRAG/Agentic) + validation + retry
- L4: Merge partitions → final Python scripts + report

---

## KEY FILES

### Backend Core
| File | Role |
|------|------|
| `backend/api/main.py` | FastAPI app, CORS, router includes, seed data, health endpoint |
| `backend/api/database.py` | SQLAlchemy models: UserRow, ConversionRow, ConversionStageRow, KBEntryRow, KBChangelogRow, AuditLogRow, CorrectionRow, NotificationRow |
| `backend/api/auth.py` | JWT (HS256), bcrypt, 24h expiry. Secret: `CODARA_JWT_SECRET` env var |
| `backend/api/schemas.py` | Pydantic schemas for all API I/O |
| `backend/api/routes/conversions.py` | Upload, start, poll, download, corrections. REAL pipeline called via BackgroundTasks |
| `backend/api/routes/auth.py` | /login, /register, /me, /github-callback |
| `backend/api/routes/knowledge_base.py` | KB CRUD + semantic search |
| `backend/api/routes/admin.py` | Admin-only: users, audit logs, system health |
| `backend/api/routes/analytics.py` | Conversion stats, time-series |
| `backend/api/routes/notifications.py` | User notifications CRUD |
| `backend/api/routes/settings.py` | User settings update |

### Pipeline Core
| File | Role |
|------|------|
| `backend/partition/orchestration/orchestrator.py` | `PartitionOrchestrator` — LangGraph StateGraph, 8 node methods, Redis checkpointing every 50 blocks |
| `backend/partition/orchestration/state.py` | `PipelineState` TypedDict, `PipelineStage` enum, `PipelineStateValidator` |
| `backend/partition/orchestration/audit.py` | `LLMAuditLogger` → DuckDB `analytics.duckdb` |
| `backend/partition/orchestration/checkpoint.py` | `RedisCheckpointManager` — save/find/clear |
| `backend/partition/orchestration/telemetry.py` | Azure Monitor / OpenTelemetry wrappers |
| `backend/partition/models/partition_ir.py` | `PartitionIR` — core unit of work (block_id, file_id, partition_type, source_code, line_start/end, risk_level, dependencies, metadata, RAPTOR back-links) |
| `backend/partition/models/enums.py` | `PartitionType` (10 types), `RiskLevel` (LOW/MOD/HIGH/UNCERTAIN), `ConversionStatus`, `PartitionStrategy` |
| `backend/partition/models/conversion_result.py` | `ConversionResult` |
| `backend/partition/models/file_metadata.py` | `FileMetadata` |
| `backend/partition/base_agent.py` | `BaseAgent` ABC with `with_retry` decorator |
| `backend/partition/utils/llm_clients.py` | `get_azure_openai_client()`, `get_groq_openai_client()`, `get_deployment_name(tier)` |
| `backend/partition/utils/retry.py` | `RateLimitSemaphore`, `CircuitBreaker`; globals: `azure_limiter`, `azure_breaker`, `groq_limiter`, `groq_breaker` |

### Pipeline Stage Files
| Stage | Key File |
|-------|----------|
| file_process | `partition/entry/file_processor.py` (orchestrates file_analysis + registry + cross_file_deps) |
| streaming | `partition/streaming/pipeline.py` → `run_streaming_pipeline()` wires `StreamAgent` → `StateAgent` via asyncio.Queue |
| streaming FSM | `partition/streaming/state_agent.py` (FSM), `partition/streaming/stream_agent.py` (reader) |
| chunking | `partition/chunking/chunking_agent.py` → `BoundaryDetectorAgent` + `PartitionBuilder` |
| boundary | `partition/chunking/boundary_detector.py` — deterministic (lark/regex, ~80%) + LLM fallback via `LLMBoundaryResolver` |
| raptor | `partition/raptor/raptor_agent.py` → `NomicEmbedder` + `GMMClusterer` + `ClusterSummarizer` + `RAPTORTreeBuilder` |
| risk_routing | `partition/complexity/risk_router.py` → `ComplexityAgent` + `StrategyAgent` |
| persist_index | `partition/persistence/persistence_agent.py` + `partition/index/index_agent.py` (NetworkX) |
| translation | `partition/translation/translation_pipeline.py` → `TranslationAgent` + `ValidationAgent` |
| translation core | `partition/translation/translation_agent.py` — full RAG routing + Azure/Groq LLM calls + cross-verify + Reflexion |
| merge | `partition/merge/merge_agent.py` → `ScriptMerger` + `ImportConsolidator` + `DependencyInjector` + `ReportAgent` |

### RAG Subsystem
| File | Role |
|------|------|
| `partition/rag/router.py` | `RAGRouter` — selects Static/GraphRAG/Agentic per partition |
| `partition/rag/static_rag.py` | LOW risk, no deps → KNN from LanceDB |
| `partition/rag/graph_rag.py` | Cross-file deps / SCC members → graph traversal |
| `partition/rag/agentic_rag.py` | MOD/HIGH/UNCERTAIN → multi-step retrieval, escalated k |
| `partition/prompts/manager.py` | `PromptManager` → Jinja2 templates |
| `partition/prompts/templates/` | `translation_static.j2`, `translation_agentic.j2`, `translation_graph.j2`, `cross_verify.j2`, `reflection.j2`, `entity_extraction.j2` |
| `partition/translation/kb_query.py` | `KBQueryClient` — LanceDB semantic search (cosine, 768-dim Nomic) |
| `partition/translation/failure_mode_detector.py` | 6 failure mode rules detection |
| `partition/kb/kb_writer.py` | `KBWriter` — LanceDB table `sas_python_examples`, 16-field schema, IVF index |

### Knowledge Base
| Path | Role |
|------|------|
| `backend/knowledge_base/gold_standard/` | 45+ `.sas` + `.gold.json` pairs for benchmark |
| `backend/scripts/generate_kb_pairs.py` | Azure+Groq KB pair generation |
| `backend/scripts/expand_kb.py` | Batch KB expansion |
| `backend/scripts/kb_rollback.py` | Version rollback |

### Frontend
| File | Role |
|------|------|
| `frontend/src/lib/api.ts` | Thin fetch wrapper, JWT Bearer via localStorage `codara_token`, `/api` proxy |
| `frontend/src/store/conversion-store.ts` | Zustand store — upload, start, poll (1.2s interval), stopPolling |
| `frontend/src/store/user-store.ts` | Auth state |
| `frontend/src/types/index.ts` | All TS types (Conversion, SasFile, PipelineStageInfo, etc.) |
| `frontend/src/pages/Workspace.tsx` | Main conversion UI with GitHub-style side-by-side diff view |
| `frontend/src/pages/Dashboard.tsx` | User dashboard |
| `frontend/src/pages/admin/` | Admin pages: Users, KBManagement, KBChangelog, AuditLogs, SystemHealth, PipelineConfig, FileRegistry |

---

## DATA MODELS

### SQLite (API DB) — `backend/codara_api.db`
- `users`: id, email, name, hashed_password, role(admin/user/viewer), status, conversion_count, default_runtime, email_notifications, email_verified, github_id
- `conversions`: id, user_id, file_name, status(queued/running/completed/partial/failed), runtime, duration, accuracy, sas_code, python_code, validation_report, merge_report
- `conversion_stages`: id, conversion_id, stage, status(pending/running/completed/failed/skipped), latency, retry_count, warnings(JSON), description, started_at, completed_at
- `kb_entries`: id, sas_snippet, python_translation, category, confidence
- `kb_changelog`: id, entry_id, action(add/edit/rollback/delete), user, timestamp, description
- `audit_logs`: id, model, latency, cost, prompt_hash, success, timestamp
- `corrections`: id, conversion_id, corrected_code, explanation, category
- `notifications`: id, user_id, title, message, type(info/success/warning/error), read

### LanceDB — `lancedb_data/` (separate from SQLite)
- Table: `sas_python_examples` — 16 fields incl. 768-dim embedding, verified bool, complexity_tier, failure_mode, verification_score, version, superseded_by

### DuckDB — `analytics.duckdb`
- `conversion_results`: conversion_id, block_id, file_id, python_code[:10000], imports, status, llm_confidence, failure_mode_flagged, model_used, kb_examples_used, retry_count, trace_id
- `llm_calls`: LLM audit logs
- `kb_changelog`: KB version history

### PartitionIR (in-memory, Pydantic)
- block_id(UUID), file_id(UUID), partition_type(PartitionType), source_code, line_start, line_end, risk_level, conversion_status, dependencies(list[UUID]), metadata(dict), raptor_leaf/cluster/root_id

---

## LLM CONFIGURATION

### Env Vars Required
```
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=2024-10-21
AZURE_OPENAI_DEPLOYMENT_MINI=gpt-4o-mini   # for LOW risk
AZURE_OPENAI_DEPLOYMENT_FULL=gpt-4o        # for MOD/HIGH risk
GROQ_API_KEY=                               # fallback + cross-verifier
CODARA_JWT_SECRET=                          # JWT signing secret
REDIS_URL=redis://localhost:6379/0
```

### LLM Routing Logic (TranslationAgent)
- LOW risk → Azure GPT-4o-mini (fast/cheap)
- MOD/HIGH/UNCERTAIN risk → Azure GPT-4o (quality)
- Cross-verify (Prompt C) → Groq LLaMA-3.1-70b (independent context via `get_groq_openai_client`)
- Reflexion retries → Groq LLaMA-3.1-70b
- Fallback chain: Azure → Groq 70B → PARTIAL status
- Circuit breaker: 5 failures → open 60s (Azure), 3 failures → open 120s (Groq)
- Rate limiter: 10 concurrent (Azure), 3 concurrent (Groq)

### Instructor Usage
- `instructor.from_openai(client)` wraps OpenAI clients for structured output
- `TranslationOutput`, `CrossVerifyOutput` are Pydantic models for structured LLM responses

---

## PIPELINE STAGE NAMING MISMATCH (KNOWN)

Frontend `types/index.ts` stages: `file_process, sas_partition, strategy_select, translate, validate, repair, merge, finalize`
Backend `conversions.py` STAGES list: `["file_process", "sas_partition", "strategy_select", "translate", "validate", "repair", "merge", "finalize"]`
Actual orchestrator nodes: `file_process, streaming, chunking, raptor, risk_routing, persist_index, translation, merge`

**The API layer maps real pipeline stages to these 8 display names for the frontend.** The frontend polls `/api/conversions/{id}` every 1.2s.

---

## TECH STACK

### Backend
- Python 3.11+
- FastAPI 0.115 + uvicorn (ASGI)
- LangGraph 0.2 (StateGraph, linear pipeline)
- SQLAlchemy 2.0 (SQLite, WAL mode, FK enforced)
- Pydantic 2.11
- structlog 25.1 (structured JSON logging)
- LanceDB 0.22 + PyArrow 20 (vector KB, 768-dim Nomic)
- DuckDB 1.3 (LLM audit/analytics)
- NetworkX 3.5 (dependency graph, SCC detection)
- sentence-transformers 4.1 + torch 2.7 (NomicEmbedder, CPU)
- scikit-learn 1.6 (ComplexityAgent ML calibration)
- Redis 5.2 (checkpointing)
- Jinja2 3.1 (prompt templates)
- instructor 1.8 (structured LLM output)
- tiktoken 0.9 (token counting)
- lark 1.2 (SAS grammar parser)
- python-jose + passlib[bcrypt] (JWT + password hashing)
- azure-monitor-opentelemetry + opentelemetry-api (telemetry)
- markdown2 (merge reports)

### Frontend
- React 18 + TypeScript
- Vite (bundler, proxy /api → :8000)
- Tailwind CSS + shadcn/ui components
- Zustand (state management: conversion-store, user-store, theme-store)
- React Router v6
- lucide-react (icons)
- framer-motion (animations in Workspace)
- bun (package manager, lockfile: bun.lockb)

### Infrastructure
- Docker Compose: redis:7-alpine + backend(Dockerfile) + frontend(nginx)
- Backend port: 8000, Frontend port: 8080 (nginx) / 5173 (dev)
- CI: GitHub Actions — test (pytest) + benchmark (gold standard) + docker-build
- CodeQL security scanning
- Dependabot: monthly

---

## CODING CONVENTIONS

1. **`from __future__ import annotations`** — at top of every Python file
2. **structlog** for all logging — `log = structlog.get_logger()`, structured key=value args
3. **Pydantic v2** models throughout — `BaseModel`, `Field`, `model_dump()`
4. **`async def process(...)`** on every agent — agents are async
5. **Error isolation** — node failures append to `state["errors"]` or `state["warnings"]`, never crash pipeline (L2-A is the only fatal exception)
6. **`_get_agent(key, factory)`** — agent cache in orchestrator, avoid re-instantiation
7. **`asyncio.to_thread()`** for sync instructor calls (bridges async context with sync instructor API)
8. **`with_retry` decorator** from `base_agent.py` for external calls
9. **TypedDict** for LangGraph state (not Pydantic, per LangGraph requirement)
10. **Import pattern**: lazy imports inside node methods (`from partition.X import Y`) to avoid circular imports
11. **File IDs**: `f"file-{uuid.uuid4().hex[:8]}"` format for upload IDs
12. **SQLite datetime**: stored as ISO string (`datetime.now(timezone.utc).isoformat()`)
13. **Frontend API**: all calls via `api.get/post/put/delete()` from `lib/api.ts`; token in localStorage `codara_token`
14. **Polling**: `setInterval(1200ms)` stops when status ∈ {completed, failed, partial}

---

## FRAGILE AREAS

1. **`asyncio.to_thread()` + instructor**: instructor calls are sync; wrapped in `to_thread`. If event loop is closed or wrong, fails silently → PARTIAL status.
2. **LanceDB cold start**: `NomicEmbedder` loads torch model on first call (slow). If Redis OR LanceDB unavailable → graceful degradation but no KB retrieval.
3. **SQLite WAL + concurrent writes**: single SQLite file for API db. High concurrency → potential lock contention. WAL mode mitigates.
4. **Pipeline stage name mapping**: frontend expects 8 named stages; backend writes real stage names. `_conv_to_out()` in `conversions.py` maps via STAGES list — if stage name not in list, sorts to end (index 99).
5. **`_translate_sas_to_python()` in `conversions.py`**: standalone LLM function separate from full pipeline; used for quick single-file conversions in the API. Has its own `PromptManager` instantiation.
6. **RAPTOR on small files**: skips clustering if `partitions < 2`. GMM clustering requires `n_samples >= n_components`.
7. **Redis checkpointing**: if Redis unavailable, orchestrator continues in degraded mode (no checkpoints). Reconnection not automatic.
8. **AZURE_OPENAI_ENDPOINT/KEY missing**: `get_azure_openai_client()` raises `RuntimeError` caught in `TranslationAgent.__init__` → `azure_client = None` → falls back to Groq; if Groq also missing → all translations become PARTIAL.
9. **Test 8 in test_streaming.py**: hardcoded path `C:\Users\labou\Desktop\stagePfe\advanced_code.sas` — Windows-only, skipped if missing.
10. **`merge_agent.process()`**: receives `cr.model_dump()` dicts, not ConversionResult objects — fragile if ConversionResult schema changes.

---

## API ENDPOINTS

### Auth
- `POST /api/auth/login` → `{access_token, token_type, user}`
- `POST /api/auth/register` → `{access_token, token_type, user}`
- `GET /api/auth/me` → User
- `POST /api/auth/github-callback`

### Conversions
- `POST /api/conversions/upload` → `list[SasFileOut]` (saves to `backend/uploads/file-{hex8}/`)
- `POST /api/conversions/start` → `ConversionOut` (triggers background pipeline)
- `GET /api/conversions` → `list[ConversionOut]`
- `GET /api/conversions/{id}` → `ConversionOut`
- `GET /api/conversions/{id}/download` → zip (python_code + report)
- `GET /api/conversions/{id}/stream` → SSE (streaming status)
- `POST /api/conversions/{id}/corrections` → submit human correction → triggers KB update
- `GET /api/conversions/{id}/partitions` → `list[PartitionOut]`

### Knowledge Base
- `GET /api/knowledge-base` → `list[KBEntryRow]`
- `POST /api/knowledge-base` → create entry
- `PUT /api/knowledge-base/{id}` → update
- `DELETE /api/knowledge-base/{id}` → delete
- `GET /api/knowledge-base/changelog` → history

### Admin (role=admin required)
- `GET /api/admin/users` → all users
- `PUT /api/admin/users/{id}` → update user
- `DELETE /api/admin/users/{id}`
- `GET /api/admin/audit-logs`
- `GET /api/admin/system-health`
- `GET /api/admin/pipeline-config`
- `PUT /api/admin/pipeline-config`
- `GET /api/admin/file-registry`

### Other
- `GET /api/analytics` → AnalyticsData[]
- `GET /api/notifications` → user notifications
- `PATCH /api/notifications/{id}/read`
- `GET /api/settings` / `PUT /api/settings`
- `GET /api/health` → `{status: "ok", version: "3.0.0"}`

---

## DEFAULT CREDENTIALS (seeded)
- Admin: `admin@codara.dev` / `admin123!`
- User: `user@codara.dev` / `user123!`

---

## TEST STRUCTURE

```
backend/tests/
├── test_streaming.py          # StreamAgent, StateAgent, pipeline perf
├── test_boundary_detector.py  # BoundaryDetector + LLM resolver
├── test_complexity_agent.py   # ComplexityAgent ML scoring
├── test_strategy_agent.py     # StrategyAgent routing
├── test_rag.py                # RAGRouter, 3 paradigms
├── test_raptor.py             # RAPTOR tree building
├── test_translation.py        # TranslationAgent, cross-verify, reflexion
├── test_orchestration.py      # Full pipeline integration
├── test_persistence.py        # SQLite persistence
├── test_evaluation.py         # Flat index + ablation queries
├── test_merge_retraining.py   # MergeAgent + KB feedback loop
├── test_file_analysis.py      # FileAnalysisAgent
├── test_cross_file_deps.py    # CrossFileDepsResolver
├── test_data_lineage.py       # DataLineageExtractor
├── test_registry_writer.py    # RegistryWriterAgent
├── test_robustness_kb.py      # KB rollback/versioning
├── test_integration.py        # End-to-end API tests
├── regression/
│   └── test_ablation.py       # RAPTOR vs flat index ablation
backend/benchmark/
└── boundary_benchmark.py      # Gold standard boundary accuracy
```

**Run**: `cd backend && python -m pytest tests/ -v --tb=short`
**CI target**: tests pass; no coverage threshold currently enforced in CI yaml (target ≥80%)

---

## REMAINING WORK (Week 14 state)

Based on `docs/planning/week-14.md`:
- [ ] Polish ablation plots (`scripts/analyze_ablation.py --db ablation.db --plots`)
- [ ] Expand KB: 330 → 380 pairs (50 more, targeting weak categories)
- [ ] Finalize README.md (≥100 lines, Quick Start section)
- [ ] Final test suite run with coverage report
- [ ] Defense slides (`docs/defense_slides.pptx`)
- [ ] Demo video (`docs/demo_video.mp4`)
- [ ] `scripts/verify_deliverables.py` — missing files: `lancedb_data/`, `benchmark/complexity_training.csv`, `docs/ablation_results.md`, `docs/raptor_paper_notes.md`

---

## ENVIRONMENT / RUN

```bash
# Development
cd backend && uvicorn api.main:app --reload --port 8000
cd frontend && bun run dev   # :5173, proxies /api → :8000

# Docker
docker compose up --build    # redis :6379, backend :8000, frontend :8080

# Tests
cd backend && python -m pytest tests/ -v

# Pipeline CLI
cd backend && python scripts/run_pipeline.py path/to/file.sas

# KB generation
cd backend && python scripts/generate_kb_pairs.py
```

---

## GOLD STANDARD CORPUS

`backend/knowledge_base/gold_standard/` — 45 pairs:
- `gs_*` (prefix): basic (data step, retain, merge, first/last, etl, multi-output, hash, proc_means, proc_freq, sql, macro, do_loop, include, filename)
- `gsh_*` (hard): enterprise etl, macro framework, warehouse load, clinical trial, fraud detection, regulatory report, migration suite, batch processor, analytics pipeline, financial recon, scoring engine, data governance, portfolio analysis, multi-source merge, complete report
- `gsm_*` (medium): financial summary, customer segmentation, claims processing, inventory analysis, employee report, survey analysis, time series, data cleaning, cohort analysis, marketing roi, risk scoring, supply chain, sales dashboard, compliance check, ab testing, data reconciliation, etl incremental, macro reporting, longitudinal, audit trail

Each `.gold.json` has expected partition types, boundaries, and complexity scores.

---

## WEEK-BY-WEEK BUILD HISTORY (from planning branch)

| Week | Layer | Key Deliverable | Tests (cumulative) | Commit |
|------|-------|-----------------|--------------------|--------|
| 1-2 | L2-A | FileAnalysisAgent, CrossFileDepsResolver, RegistryWriterAgent, DataLineageExtractor, 50-file gold corpus (721 blocks) | ~20 | `b2b2dd4` |
| 2-3 | L2-B | StreamAgent, StateAgent, streaming pipeline, backpressure | ~35 | — |
| 3-4 | L2-C | BoundaryDetector (lark/regex + LLM), BoundaryDetectorAgent | ~60 | — |
| 4 | L2-D | ComplexityAgent (ML calibrated), StrategyAgent | ~80 | — |
| 5-6 | L2-C | NomicEmbedder, GMMClusterer, ClusterSummarizer, RAPTORTreeBuilder, RAPTORPartitionAgent | ~100 | — |
| 7 | L2-E | PersistenceAgent (#10), IndexAgent (#11), NetworkXGraphBuilder, DuckDB 7-table schema | 115 | `1fcba49` |
| 8 | Orch | PartitionOrchestrator (#15, 9-node graph), RedisCheckpointManager, LLMAuditLogger | 126 | — |
| 9 | Robust+KB | RateLimitSemaphore, CircuitBreaker, MemoryMonitor, KBWriter (LanceDB), kb_changelog, generate_kb_pairs.py. **Azure OpenAI migration** (primary, replaced Ollama/Groq-primary) | 144 | `be15d49` |
| 10 | L3 | TranslationAgent (#12, 3-tier RAG), ValidationAgent (#13, sandbox exec), TranslationPipeline | 169 | `b542c25` |
| 11 | L4+CL | ImportConsolidator, DependencyInjector, ScriptMerger, ReportAgent (#14), FeedbackIngestionAgent, ConversionQualityMonitor, RetrainTrigger. KB → 330 pairs | 191 | `2c5a6da` |
| 12 | Eval | Ablation study infra: flat_index.py, query_generator.py, ablation_runner.py, init_ablation_db.py, analyze_ablation.py | 198 | `dbaebf1` |
| 13 | Restructure | **11→8 orchestrator nodes, v3.0.0**. Introduced 8 composite node-agents (facade pattern), each delegating to 1–4 specialist sub-agents internally. Azure Monitor telemetry, GitHub Actions CI/CD, CodeQL, Docker. 44+20 audit fixes. Added MergeAgent node (7→8). | 221 | — |
| 14 | Buffer | Polish + defense (in progress) | — | — |

### Key Architecture Changes by Week
- **Week 9**: Groq demoted from primary to fallback+verifier; Azure OpenAI becomes primary. Old plans (Ollama 8B for LOW, Groq 70B for MOD/HIGH) replaced.
- **Week 13 restructure**: Orchestrator reduced from 11 nodes to 7, then 8. Introduced 8 composite node-agents (facade pattern) — sub-agents still exist internally, the orchestrator sees 8 nodes.
- **Post-audit fix #15**: `ValidationAgent` exec sandbox changed from `threading.Thread` (leaky) to `multiprocessing.Process` + `.kill()` (true isolation).
- **Post-audit fix #8**: `config_manager.py` rewritten — source YAML is now read-only, runtime state in separate `runtime_state.yaml`.
- **Post-audit fix #2**: Dockerfile `COPY config/` corrected to `COPY sas_converter/config/` (was broken due to rename).

---

## PIPELINE NODE MAP (Week 13)

Each orchestrator node is a **composite agent (facade)** that delegates to specialist sub-agents.
The sub-agent files still exist; the node-agent is a thin wrapper that calls them in sequence.

| Node-agent (orchestrator sees 8) | Sub-agents called internally | Node in graph |
|-----------------------------------|------------------------------|---------------|
| `FileProcessor` | FileAnalysisAgent → CrossFileDependencyResolver → RegistryWriterAgent | file_process |
| `StreamingParser` (via `pipeline.py`) | StreamAgent → StateAgent | streaming |
| `ChunkingAgent` | BoundaryDetectorAgent → PartitionBuilderAgent | chunking |
| `RAPTORPartitionAgent` | NomicEmbedder → GMMClusterer → ClusterSummarizer → RAPTORTreeBuilder | raptor |
| `RiskRouter` | ComplexityAgent → StrategyAgent | risk_routing |
| `PersistenceAgent + IndexAgent` | PersistenceAgent + IndexAgent (1 node, 2 agents) | persist_index |
| `TranslationPipeline` | TranslationAgent → ValidationAgent | translation |
| `MergeAgent` | ScriptMerger (ImportConsolidator + DependencyInjector) → ReportAgent | merge |

---

## EVALUATION TARGETS (from PLANNING.md)

| Metric | Target | Layer |
|--------|--------|-------|
| Boundary accuracy | > 90% on 721-block gold corpus | L2-C |
| Streaming perf | 10K-line file < 2s, < 100 MB peak | L2-B |
| Complexity ECE | < 0.08 on held-out 20% | L2-D |
| Translation success | ≥ 70% | L3 |
| Syntax-valid merged scripts | ≥ 95% | L4 |
| RAPTOR hit-rate@5 | > 0.82 | L2-C |
| RAPTOR MRR | > 0.60 | L2-C |
| RAPTOR advantage on MOD/HIGH | ≥ 10% vs flat | Eval |
| KB pairs (current) | 330 verified | KB |
| KB pairs (target) | 380 (Week 14) | KB |
| Test coverage | ≥ 80% | All |

---

## VALIDATION AGENT SANDBOX (security-critical)

`partition/translation/validation_agent.py` uses `multiprocessing.Process` to sandbox `exec()`:
- Removed builtins: `open`, `__import__`, `exec`, `eval`, `compile`, `exit`, `quit`, `input`, `breakpoint`
- Killed via `.kill()` on timeout (not `.join(timeout)` which leaks threads)
- Module-level function required for pickling (not lambda or inner function)
- Windows-compatible (no `signal.alarm`)

---

## PLANNING BRANCH EXTRA FILES

The `planning` branch contains files not merged to main:
- `planning/` — all weekly Done files + visualization scripts
- `sas_converter/` — old package path (pre-rename), contains debug scripts
- `sas_converter/scripts/debug/` — 40+ debug scripts for boundary detection development
- `azure_evaluation.md` — enterprise architecture review (motivation for Azure migration)
- `trello_kanban.md` — Trello board export
- `checklist.md`, `checklist_week2-3.md` — completion checklists

---

## KNOWN ISSUES / NOTES

- `docs/kanbanV2.md` is untracked (in git status) — work-in-progress kanban
- `backend/tests/test_streaming.py` has a modified state (M in git status) — check before committing
- Week 14 planning docs reference `ollama` as LLM (outdated); actual implementation uses Azure OpenAI (migrated Week 9); Groq is fallback only
- `PySpark` target is supported in pipeline (`target_runtime` field exists) but frontend only shows `python` (`TargetRuntime = "python"` in types/index.ts)
- `github_id` OAuth field exists in UserRow but GitHub OAuth callback is a stub
- CORS allows `localhost:8080`, `localhost:5173`, `127.0.0.1:8080` — add prod domain when deploying
- CI originally referenced `sas_converter/` path; fixed in Week 13 to `backend/`
- `APPLICATIONINSIGHTS_CONNECTION_STRING` env var optional — telemetry is no-op when absent
