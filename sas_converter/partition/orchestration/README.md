# Orchestration Layer

LangGraph StateGraph pipeline with Redis checkpointing and DuckDB audit logging.

## Agents

| # | Agent | File | Purpose |
|---|-------|------|---------|
| 15 | `PartitionOrchestrator` | `orchestrator.py` | LangGraph StateGraph wiring all L2 agents end-to-end |
| 16 | `LLMAuditLogger` | `audit.py` | DuckDB-backed audit logging for every LLM call |

## Files

| File | Description |
|------|-------------|
| `state.py` | `PipelineStage` enum (12 stages: INIT → COMPLETE/ERROR) + `PipelineState` TypedDict |
| `audit.py` | Context-manager LLM audit → DuckDB `llm_audit` table; tracks latency, prompt/response hashes |
| `checkpoint.py` | `RedisCheckpointManager` — saves state every 50 blocks; 24h TTL; graceful degradation |
| `orchestrator.py` | LangGraph `StateGraph` with 9 nodes; error isolation per agent; linear pipeline |

## Architecture

```
Input: list of .sas paths
        |
        v
  PartitionOrchestrator (#15)  [LangGraph StateGraph]
    |
    |-- Node 1: entry_analysis      (FileAnalysisAgent)
    |-- Node 2: cross_file_deps     (CrossFileDependencyResolver)
    |-- Node 3: registry_write      (RegistryWriterAgent)
    |-- Node 4: streaming           (StreamAgent + StateAgent)
    |-- Node 5: boundary_detection  (BoundaryDetectorAgent)
    |-- Node 6: raptor_clustering   (RAPTORPartitionAgent)
    |-- Node 7: complexity_scoring  (ComplexityAgent + StrategyAgent)
    |-- Node 8: persistence         (PersistenceAgent)
    +-- Node 9: indexing            (IndexAgent)
        |
        v
  PipelineState (TypedDict)
    -> file_metadata, partitions, raptor_nodes, dag, sccs, hop_cap
    -> stage tracking (INIT -> ... -> COMPLETE)
        |
    Checkpointing: Redis (every 50 blocks, TTL 24h)
    Audit: DuckDB llm_audit table (every LLM call)
```

## Pipeline Stages (12)

| Stage | Description |
|-------|-------------|
| INIT | Pipeline start |
| FILE_ANALYSIS | Scanning .sas files |
| DEPENDENCY_RESOLUTION | Cross-file deps |
| REGISTRY_WRITE | Persist to SQLite |
| STREAMING | Async line-by-line parse |
| BOUNDARY_DETECTION | Rule-based + LLM detection |
| RAPTOR_CLUSTERING | Semantic clustering |
| COMPLEXITY_SCORING | Risk assessment |
| STRATEGY_ROUTING | Conversion strategy |
| PERSISTENCE | Write partitions to DB |
| INDEXING | Build dependency DAG |
| COMPLETE | Pipeline success |
| ERROR | Pipeline failure (with error details) |

## Key Features

- **LangGraph StateGraph** — Typed state flows through nodes; compile-time validation
- **Error isolation** — Each node catches exceptions, sets stage to ERROR with details
- **Redis checkpointing** — Resume from last checkpoint on failure (degraded mode if Redis unavailable)
- **DuckDB audit** — Every LLM call logged with latency, token count, prompt/response hashes
- **12-stage tracking** — Full observability into pipeline progress

## Dependencies

`langgraph` (StateGraph, END), `redis` (optional, lazy import), `duckdb`, `structlog`
