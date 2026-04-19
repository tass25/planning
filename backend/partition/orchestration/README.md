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

## Exception Handling

The orchestration layer is designed to **never crash** — it degrades gracefully when external dependencies are unavailable.

### DuckDB Audit (`audit.py`)

| Protection | Detail |
|-----------|--------|
| **Auto-create table** | `_get_duckdb()` runs `CREATE TABLE IF NOT EXISTS llm_audit (...)` on first connection. The `persist()` method never fails because the table doesn't exist. If the DuckDB file is corrupted and can't connect, it logs a warning via `structlog` and raises — the caller's existing `try/except` in `persist()` catches it and the audit entry is simply skipped. |
| **Timer guard** | `_LLMCallTracker.succeed()` and `fail()` check `if self._start_time is not None` before computing `time.perf_counter() - self._start_time`. This prevents a `TypeError` if `start()` was never called (e.g., if the context manager is used incorrectly). |
| **Persist isolation** | `persist()` wraps the DuckDB `INSERT` in `try/except`. A failure to write an audit row is logged but never propagates — the LLM call result is still returned. |

### Orchestrator (`orchestrator.py`)

| Protection | Detail |
|-----------|--------|
| **Memory monitor** | `MemoryMonitor()` instantiation is wrapped in `try/except`. If `psutil` or other system-level dependencies are missing, `self.memory_monitor` is set to `None` and execution continues. |
| **Memory guards** | `configure_memory_guards()` (which sets OMP_NUM_THREADS, CUDA limits, etc.) is wrapped in `try/except`. Missing environment variables or OS-level restrictions are logged and ignored. |
| **Error classification** | L2-A (`file_process`) failure is treated as **fatal** — it raises `RuntimeError` because no downstream work is possible without file metadata. All other nodes (L2-B through L4) use error isolation: they append to `state["errors"]` and continue. |
| **Agent cache** | The `_agents` dictionary caches agent instances. If an agent constructor fails, the error propagates to the node's own `try/except` block and is classified as a non-fatal error. |

### Checkpointing (`checkpoint.py`)

| Protection | Detail |
|-----------|--------|
| **Degraded mode** | On startup, `RedisCheckpointManager` pings Redis. If the connection fails, `self.available = False` and every public method (`save_checkpoint`, `find_latest_checkpoint`, `clear_checkpoints`) becomes a safe no-op. The pipeline runs without checkpointing. |
| **Per-operation isolation** | Each `save`, `find`, and `clear` operation wraps the Redis call in its own `try/except`. A transient Redis failure during one checkpoint doesn't stop subsequent operations. |

### LLM Clients (`utils/llm_clients.py`)

| Protection | Detail |
|-----------|--------|
| **Missing env vars** | `get_azure_openai_client()` and `get_groq_openai_client()` return `None` when keys are absent rather than crashing. The TranslationAgent skips the unavailable tier and moves to the next one in the chain. |
| **Missing packages** | Each LLM client factory is wrapped in `try/except ImportError`. If the package isn't installed the client comes back `None` and the tier is skipped silently. |
| **Retry + circuit breaker** | The `retry.py` module provides `with_retry` (exponential backoff) and `CircuitBreaker` (fail-fast after N consecutive failures) for Azure and Groq. Ollama has its own timeout guard. |

