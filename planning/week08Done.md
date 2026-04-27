# Week 8 Done: Orchestration -- PartitionOrchestrator + Redis Checkpoints

> **Layer**: Orchestration (Agent #15)  
> **Branch**: `main`  
> **Status**: COMPLETE  
> **Tests**: 126 passing (11 new orchestration + 115 existing)  
> **Dependencies added**: langgraph >= 0.1, redis >= 5.0  

---

## Summary

Built the **PartitionOrchestrator** (#15) using LangGraph's `StateGraph`, unifying all 11 L2 agents into a single end-to-end pipeline with:

- **Redis checkpointing** every 50 blocks (24h TTL, degraded mode if Redis unavailable)
- **DuckDB LLM audit logging** for every external model call
- **Error isolation** -- individual agent failures produce warnings, not pipeline crashes
- **CROSS_FILE_RESOLVE** state flows through the entire pipeline

---

## Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `partition/orchestration/__init__.py` | Package init | 2 |
| `partition/orchestration/state.py` | `PipelineStage` enum (12 stages) + `PipelineState` TypedDict | 75 |
| `partition/orchestration/checkpoint.py` | `RedisCheckpointManager` -- save/find/clear with TTL | 120 |
| `partition/orchestration/audit.py` | `LLMAuditLogger` + `_LLMCallTracker` -- context manager for DuckDB logging | 115 |
| `partition/orchestration/orchestrator.py` | `PartitionOrchestrator` -- LangGraph StateGraph with 9 nodes | 320 |
| `scripts/run_pipeline.py` | CLI entry point for the full pipeline | 95 |
| `tests/test_orchestration.py` | 11 test cases (state, checkpoint, audit, graph) | 180 |
| `planning/week08viz.py` | 4-panel visualization (DAG, waterfall, checkpoints, audit) | 230 |

---

## Architecture

```
Input: SAS file path(s) / directory
         |
         v
 +----------------------------+
 |  PartitionOrchestrator     |  <-- LangGraph StateGraph
 |  (Agent #15)               |
 |                            |
 |  +-- L2-A ---------------+ |     Redis Checkpoint
 |  | FileAnalysisAgent      +-+--> partition:{fid}:checkpoint:{n}
 |  | CrossFileDependency    | |    TTL 24h, every 50 blocks
 |  | RegistryWriterAgent    | |
 |  +------------------------+ |
 |         |                   |     DuckDB llm_audit
 |  +-- L2-B ---------------+ |---> call_id, agent, model,
 |  | run_streaming_pipeline | |     latency_ms, success, tier
 |  | (StreamAgent+StateAgent| |
 |  +------------------------+ |
 |         |                   |
 |  +-- L2-C ---------------+ |
 |  | BoundaryDetectorAgent  | |
 |  | PartitionBuilderAgent  | |
 |  | RAPTORPartitionAgent   | |
 |  +------------------------+ |
 |         |                   |
 |  +-- L2-D ---------------+ |
 |  | ComplexityAgent        | |
 |  | StrategyAgent          | |
 |  +------------------------+ |
 |         |                   |
 |  +-- L2-E ---------------+ |
 |  | PersistenceAgent       | |
 |  | IndexAgent             | |
 |  +------------------------+ |
 |         |                   |
 |   Output: PipelineState     |
 |   -> PartitionIR[]          |
 |   -> RAPTOR tree            |
 |   -> Dependency graph       |
 |   -> SCC groups             |
 +----------------------------+
```

---

## PipelineStage Enum (12 stages)

| Stage | Description |
|-------|-------------|
| `INIT` | Pipeline initialized, state created |
| `FILE_SCAN` | L2-A: scanning .sas files, registering in SQLite |
| `CROSS_FILE_RESOLVE` | L2-A: resolving %INCLUDE, LIBNAME, &macro references |
| `STREAMING` | L2-B: streaming files through StreamAgent + StateAgent |
| `BOUNDARY_DETECTION` | L2-C: detecting block boundaries + building PartitionIR |
| `RAPTOR_CLUSTERING` | L2-C: RAPTOR semantic clustering with NomicEmbed + GMM |
| `COMPLEXITY_ANALYSIS` | L2-D: computing risk_level with LogReg + Platt scaling |
| `STRATEGY_ASSIGNMENT` | L2-D: assigning conversion strategy per block |
| `PERSISTENCE` | L2-E: writing partitions to SQLite (content-hash dedup) |
| `INDEXING` | L2-E: building dependency graph, SCC detection, hop cap |
| `COMPLETE` | Pipeline finished successfully |
| `ERROR` | Pipeline encountered a fatal error |

---

## PipelineState TypedDict Fields

```python
PipelineState = {
    # Input
    "input_paths": list[str],
    "target_runtime": str,          # "python" | "pyspark"

    # Progress
    "stage": str,                   # PipelineStage value
    "current_file_idx": int,

    # L2-A
    "file_metas": list,             # FileMetadata objects
    "file_ids": list[str],          # UUIDs
    "cross_file_deps": dict,

    # L2-B/C
    "chunks_by_file": dict,         # {file_id: chunks_with_states}
    "partitions": list,             # PartitionIR objects
    "partition_count": int,

    # L2-C RAPTOR
    "raptor_nodes": list,           # RAPTORNode objects

    # L2-D
    "complexity_computed": bool,

    # L2-E
    "persisted_count": int,
    "scc_groups": list,
    "max_hop": int,

    # Checkpointing
    "last_checkpoint_block": int,
    "checkpoint_key": str | None,

    # Error tracking
    "errors": list[str],
    "warnings": list[str],

    # Tracing
    "trace_id": str,
    "run_id": str,
}
```

---

## RedisCheckpointManager

| Feature | Detail |
|---------|--------|
| Checkpoint interval | Every 50 blocks |
| TTL | 24 hours (86400 seconds) |
| Key format | `partition:{file_id}:checkpoint:{block_num}` |
| Degraded mode | If Redis unavailable, all methods are safe no-ops |
| Resume | `find_latest_checkpoint()` scans all keys, returns highest block |
| Cleanup | `clear_checkpoints()` removes all keys for a completed file |

---

## LLM Audit Logger

| Feature | Detail |
|---------|--------|
| Storage | DuckDB `llm_audit` table |
| Interface | Context manager: `with audit.log_call(agent, model, prompt) as call:` |
| Timing | Automatic `latency_ms` via `time.perf_counter()` |
| Hashing | SHA-256 of prompt + response (first 16 chars) |
| Fields logged | call_id, agent_name, model_name, prompt_hash, response_hash, latency_ms, success, error_msg, tier, timestamp |

---

## LangGraph StateGraph

The orchestrator builds a **compiled** LangGraph `StateGraph` with 9 nodes connected linearly:

```
file_scan -> cross_file_resolve -> streaming -> boundary_detection
    -> raptor_clustering -> complexity_analysis -> strategy_assignment
    -> persistence -> indexing -> END
```

Each node:
1. Receives the full `PipelineState` dict
2. Calls the appropriate agent(s) with correct API
3. Returns a **partial update dict** merged back into state
4. Wraps agent calls in try/except for error isolation

---

## Corrected Agent API Usage

The planning doc had several API mismatches. The orchestrator uses the **actual** interfaces:

| Agent | Actual API |
|-------|-----------|
| `FileAnalysisAgent` | `.process(project_root: Path) -> list[FileMetadata]` |
| `RegistryWriterAgent` | `.process(files: list[FileMetadata], engine) -> dict` |
| `CrossFileDependencyResolver` | `.process(files, project_root, engine) -> dict` |
| `run_streaming_pipeline` | Free function: `(file_meta, trace_id=) -> list[tuple]` |
| `BoundaryDetectorAgent` | `.process(chunks_with_states, file_id) -> list[BlockBoundaryEvent]` |
| `PartitionBuilderAgent` | `.process(events) -> list[PartitionIR]` |
| `ComplexityAgent` | `.__init__()` (no trace_id), `.process(partitions) -> list[PartitionIR]` |
| `StrategyAgent` | `.process(partitions) -> list[PartitionIR]` |
| `RAPTORPartitionAgent` | `.process(partitions, file_id) -> list[RAPTORNode]` |
| `PersistenceAgent` | `.process(partitions, file_id) -> int` |
| `IndexAgent` | `.process(partitions, cross_file_deps) -> dict{dag,sccs,condensed,hop_cap}` |

---

## Tests (11 new, 126 total)

| Test Class | Tests | What It Validates |
|------------|-------|-------------------|
| `TestPipelineState` | 2 | All TypedDict fields present, 12 enum stages |
| `TestRedisCheckpoint` | 4 | Degraded mode, interval skip, fires at 0 and 50 |
| `TestLLMAuditLogger` | 2 | Success + failure context manager -> DuckDB rows |
| `TestOrchestratorGraph` | 2 | Graph compiles, has all nodes |
| `TestInitialState` | 1 | Valid initial state construction |

```
$ pytest sas_converter/tests/test_orchestration.py -v
============================= 11 passed in 2.82s ==============================
```

Full suite: **126 passed in 68s**.

---

## CLI Entry Point

```bash
# Process a directory of SAS files
python scripts/run_pipeline.py data/sas_corpus/ --target python

# Process specific files
python scripts/run_pipeline.py file1.sas file2.sas --target pyspark

# Custom Redis and DuckDB paths
python scripts/run_pipeline.py data/*.sas --redis redis://myhost:6379/1 --duckdb audit.duckdb
```

---

## Visualization (`planning/week08viz.py`)

4-panel interactive visualization:

1. **LangGraph Pipeline DAG** -- All 9 nodes color-coded by layer (L2-A through L2-E)
2. **Stage Waterfall** -- Timing breakdown showing RAPTOR_CLUSTERING as slowest (6.7s)
3. **Redis Checkpoint Timeline** -- Block-by-block checkpoint events per file
4. **DuckDB LLM Audit Summary** -- Call counts, success/failure rates, mean latency per agent

```bash
cd C:\Users\labou\Desktop\Stage
venv\Scripts\python planning\week08viz.py
```

---

## Metrics

| Metric | Result |
|--------|--------|
| New agents | 1 (PartitionOrchestrator #15) |
| Total agents | 16 |
| Pipeline nodes | 9 |
| Tests added | 11 |
| Total tests | 126 |
| Checkpoint interval | 50 blocks |
| Checkpoint TTL | 24h |
| Redis degraded mode | Yes (safe no-ops) |
| Error isolation | Yes (try/except per node) |
| LLM audit logging | Yes (DuckDB context manager) |

---

## Dependencies Added

| Package | Version Installed | Purpose |
|---------|-------------------|---------|
| `langgraph` | 1.0.10 | StateGraph orchestration |
| `redis` | 7.2.1 | Checkpoint persistence |
| `langchain-core` | 1.2.17 | LangGraph dependency |
| `langsmith` | 0.7.12 | LangGraph dependency |

---

## What's Next: Week 9 (P2 - Robustness + KB Generation)

With the full L2 pipeline orchestrated, Week 9 focuses on:
- Robustness: retry policies, circuit breakers, rate limiting
- Knowledge Base generation from conversion results
- Quality metrics tracking in DuckDB

> *P1 phase is COMPLETE. 16 agents, full L2 pipeline orchestrated with LangGraph, Redis checkpointing, DuckDB audit logging.*

---

## ☁️ Azure Migration Update (Added Week 9)

### What was used before

The `LLMAuditLogger` (`partition/orchestration/audit.py`) originally logged every LLM call **only to DuckDB** (`llm_audit` table). This was sufficient for local development — we could query latency percentiles, error rates, and cost estimates via SQL. However, there was no cloud-level observability: no dashboards, no alerting, no cross-session trends.

### Why we added Azure Application Insights

1. **Real-time monitoring**: Azure Portal provides live dashboards for LLM call latency (P50/P95/P99), error rates, and throughput — no SQL queries needed.
2. **Alerting**: App Insights can trigger email/Teams alerts when error rates spike or latency exceeds thresholds.
3. **Cross-session analytics**: DuckDB files are local and ephemeral. App Insights aggregates telemetry across all pipeline runs, all machines.
4. **$100 student credit**: App Insights ingestion is ~$2.30/GB. Our LLM audit telemetry generates <1MB/month — effectively free.
5. **Production readiness**: When deploying to Azure Container Apps (Week 14), App Insights is the native telemetry solution.

### What changed

| Change | Detail |
|--------|--------|
| Dual logging | DuckDB (primary, always) + App Insights (optional, cloud) |
| Env var | `APPINSIGHTS_CONNECTION_STRING` enables cloud telemetry |
| Dependencies | Added `azure-monitor-opentelemetry>=1.4.0`, `opencensus-ext-azure>=1.1.0` to requirements.txt |
| `LLMAuditLogger.__init__` | Added `_appinsights_enabled` flag (auto-detected from env) |
| `_LLMCallTracker.__init__` | Added `appinsights_enabled` parameter |
| `_LLMCallTracker.persist()` | After DuckDB insert, sends custom event to App Insights via `AzureLogHandler` |
| Graceful fallback | If `opencensus` import fails or App Insights connection string is missing, cloud telemetry is silently disabled |

### How it works

```python
# DuckDB (always — local analytics)
con.execute("INSERT INTO llm_audit VALUES (...)", [call_id, agent, model, ...])

# App Insights (optional — cloud telemetry)
if self._appinsights_enabled:
    az_logger.info("llm_call_completed", extra={
        "custom_dimensions": {
            "call_id": self.call_id,
            "agent_name": self.agent_name,
            "model_name": self.model_name,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "tier": self.tier,
        }
    })
```

### New env var

```bash
$env:APPINSIGHTS_CONNECTION_STRING = "InstrumentationKey=xxx;IngestionEndpoint=https://xxx.in.applicationinsights.azure.com/"
```

If not set, the audit logger works exactly as before (DuckDB only). No breaking change.
