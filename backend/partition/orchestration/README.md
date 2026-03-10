# Orchestration Layer

LangGraph StateGraph pipeline with Redis checkpointing and DuckDB audit logging.

## Pipeline (8 Nodes — v3.0)

```
file_process → streaming → chunking → raptor → risk_routing → persist_index → translation → merge → END
```

| Node | Agent | Purpose |
|------|-------|---------|
| 1 | `FileProcessor` | Scan files, register in SQLite, resolve cross-file deps |
| 2 | `StreamingParser` | Async line-by-line streaming + FSM state tracking |
| 3 | `ChunkingAgent` | Boundary detection + partition building |
| 4 | `RAPTORPartitionAgent` | Semantic clustering (NomicEmbed + GMM) |
| 5 | `RiskRouter` | Complexity scoring + strategy routing |
| 6 | `PersistenceAgent + IndexAgent` | SQLite persistence + NetworkX DAG + SCC |
| 7 | `TranslationPipeline` | LLM translation + validation + retry loop |
| 8 | `MergeAgent` | Script assembly + report generation |

## Files

| File | Description |
|------|-------------|
| `orchestrator.py` | LangGraph `StateGraph` with 8 nodes; error isolation per agent; linear pipeline |
| `state.py` | `PipelineStage` enum + `PipelineState` TypedDict |
| `audit.py` | Context-manager LLM audit → DuckDB `llm_audit` table; tracks latency, prompt/response hashes |
| `checkpoint.py` | `RedisCheckpointManager` — saves state every 50 blocks; 24h TTL; graceful degradation |
| `telemetry.py` | Azure Monitor + OpenTelemetry wrapper — `track_event()`, `track_metric()`, `trace_span()` |

## Key Features

- **LangGraph StateGraph** — Typed state flows through nodes; compile-time validation
- **Error classification** — L2-A failure is fatal (data loss); other stages degrade gracefully
- **Redis checkpointing** — Resume from last checkpoint on failure (degraded mode if Redis unavailable)
- **DuckDB audit** — Every LLM call logged with latency, token count, prompt/response hashes
- **Azure Monitor telemetry** — track_event/track_metric/trace_span (no-op when unconfigured)

## Dependencies

`langgraph` (StateGraph, END), `redis` (optional, lazy import), `duckdb`, `structlog`, `azure-monitor-opentelemetry`
