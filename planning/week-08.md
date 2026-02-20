# Week 8: Orchestration — PartitionOrchestrator + Redis Checkpoints

> **Priority**: P1  
> **Branch**: `week-08`  
> **Layer**: Orchestration  
> **Agent to build**: PartitionOrchestrator (#15)  
> **Prerequisite**: Weeks 5–7 complete (all L2 agents functional, persistence + index layers ready)  

---

## 🎯 Goal

Build the PartitionOrchestrator that ties all L2 agents into a single end-to-end pipeline using LangGraph's StateGraph. Add Redis checkpointing for fault tolerance (resume after crash) and DuckDB LLM audit logging for every external call. After this week, the full L2 pipeline runs end-to-end with `CROSS_FILE_RESOLVE` state management.

---

## Architecture Recap

```
Input: SAS file path(s)
         │
         ▼
 ┌────────────────────────┐
 │  PartitionOrchestrator │ ← LangGraph StateGraph
 │  (#15)                 │
 │                        │
 │  ┌─ L2-A ──────────┐  │     Redis Checkpoint
 │  │ FileAnalysis     │──│──── partition:{fid}:checkpoint:{n}
 │  │ CrossFileDeps    │  │     TTL 24h, every 50 blocks
 │  │ RegistryWriter   │  │
 │  └──────────────────┘  │
 │         ▼              │     DuckDB llm_audit
 │  ┌─ L2-B ──────────┐  │──── call_id, agent, model,
 │  │ StreamAgent      │  │     latency_ms, success, tier
 │  │ StateAgent       │  │
 │  └──────────────────┘  │
 │         ▼              │
 │  ┌─ L2-C ──────────┐  │
 │  │ BoundaryDetector │  │
 │  │ RAPTORPartition  │  │
 │  └──────────────────┘  │
 │         ▼              │
 │  ┌─ L2-D ──────────┐  │
 │  │ ComplexityAgent  │  │
 │  │ StrategyAgent    │  │
 │  └──────────────────┘  │
 │         ▼              │
 │  ┌─ L2-E ──────────┐  │
 │  │ PersistenceAgent │  │
 │  │ IndexAgent       │  │
 │  └──────────────────┘  │
 │         ▼              │
 │   Output: PartitionIR[]│
 │   + RAPTOR tree        │
 │   + Dependency graph   │
 └────────────────────────┘
```

---

## Tasks

### Task 1: LangGraph State Definition

**File**: `partition/orchestration/state.py`

```python
from typing import TypedDict, Optional
from enum import Enum


class PipelineStage(str, Enum):
    INIT = "INIT"
    FILE_SCAN = "FILE_SCAN"
    CROSS_FILE_RESOLVE = "CROSS_FILE_RESOLVE"
    STREAMING = "STREAMING"
    BOUNDARY_DETECTION = "BOUNDARY_DETECTION"
    RAPTOR_CLUSTERING = "RAPTOR_CLUSTERING"
    COMPLEXITY_ANALYSIS = "COMPLEXITY_ANALYSIS"
    STRATEGY_ASSIGNMENT = "STRATEGY_ASSIGNMENT"
    PERSISTENCE = "PERSISTENCE"
    INDEXING = "INDEXING"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


class PipelineState(TypedDict):
    """LangGraph state object flowing through the pipeline."""

    # Input
    input_paths: list[str]                  # SAS file paths to process
    target_runtime: str                     # "python" | "pyspark"

    # Current stage
    stage: str                              # PipelineStage value
    current_file_idx: int                   # Index into input_paths

    # L2-A outputs
    file_ids: list[str]                     # UUIDs from FileRegistry
    cross_file_deps: dict                   # {ref_raw: target_file_id}

    # L2-B/C outputs
    partitions: list                        # PartitionIR objects
    partition_count: int

    # L2-C RAPTOR outputs
    raptor_nodes: list                      # RAPTORNode objects

    # L2-D outputs (annotated on partitions)
    complexity_computed: bool

    # L2-E outputs
    persisted_count: int
    scc_groups: list                        # SCC group sets
    max_hop: int                            # Dynamic hop cap

    # Checkpointing
    last_checkpoint_block: int              # Last checkpointed block number
    checkpoint_key: Optional[str]

    # Error tracking
    errors: list[str]
    warnings: list[str]

    # Tracing
    trace_id: str
    run_id: str
```

---

### Task 2: Redis Checkpoint Manager

**File**: `partition/orchestration/checkpoint.py`

```python
import json
import redis
from typing import Optional
import structlog

logger = structlog.get_logger()


class RedisCheckpointManager:
    """
    Redis-based checkpoint for fault-tolerant processing.
    
    Key format: partition:{file_id}:checkpoint:{block_num}
    TTL: 24 hours
    Frequency: every 50 processed blocks
    
    On startup: scan for existing checkpoints → resume from highest block.
    If Redis unavailable: degraded mode (warning log, no crash).
    """

    CHECKPOINT_INTERVAL = 50   # Blocks between checkpoints
    TTL_SECONDS = 86400        # 24 hours

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.available = False
        try:
            self.client = redis.from_url(redis_url, decode_responses=True)
            self.client.ping()
            self.available = True
            logger.info("redis_connected", url=redis_url)
        except (redis.ConnectionError, redis.TimeoutError) as e:
            self.client = None
            logger.warning("redis_unavailable",
                          msg="Continuing in degraded mode (no checkpointing)",
                          error=str(e))

    def save_checkpoint(
        self,
        file_id: str,
        block_num: int,
        partition_data: list[dict],
    ) -> bool:
        """
        Save a checkpoint with serialized partition data.
        
        Only saves every CHECKPOINT_INTERVAL blocks.
        Returns True if checkpoint was saved.
        """
        if not self.available:
            return False

        if block_num % self.CHECKPOINT_INTERVAL != 0 and block_num > 0:
            return False

        key = f"partition:{file_id}:checkpoint:{block_num}"
        try:
            payload = json.dumps({
                "file_id": file_id,
                "block_num": block_num,
                "partition_count": len(partition_data),
                "partitions": partition_data,
            })
            self.client.setex(key, self.TTL_SECONDS, payload)
            logger.info("checkpoint_saved",
                       file_id=file_id, block=block_num,
                       partitions=len(partition_data))
            return True
        except Exception as e:
            logger.warning("checkpoint_save_failed",
                          file_id=file_id, error=str(e))
            return False

    def find_latest_checkpoint(self, file_id: str) -> Optional[dict]:
        """
        Find the most recent checkpoint for a file.
        
        Returns the checkpoint data, or None if no checkpoint exists.
        """
        if not self.available:
            return None

        try:
            pattern = f"partition:{file_id}:checkpoint:*"
            keys = list(self.client.scan_iter(pattern))
            if not keys:
                return None

            # Find the key with the highest block number
            latest_key = max(
                keys,
                key=lambda k: int(k.split(":")[-1])
            )
            data = self.client.get(latest_key)
            if data:
                checkpoint = json.loads(data)
                logger.info("checkpoint_found",
                           file_id=file_id,
                           block=checkpoint["block_num"])
                return checkpoint
        except Exception as e:
            logger.warning("checkpoint_scan_failed",
                          file_id=file_id, error=str(e))
        return None

    def clear_checkpoints(self, file_id: str):
        """Remove all checkpoints for a completed file."""
        if not self.available:
            return

        try:
            pattern = f"partition:{file_id}:checkpoint:*"
            keys = list(self.client.scan_iter(pattern))
            if keys:
                self.client.delete(*keys)
                logger.info("checkpoints_cleared",
                           file_id=file_id, count=len(keys))
        except Exception as e:
            logger.warning("checkpoint_clear_failed",
                          file_id=file_id, error=str(e))
```

---

### Task 3: LLM Audit Logger

**File**: `partition/orchestration/audit.py`

```python
import uuid
import hashlib
import time
from contextlib import contextmanager
from typing import Optional
import duckdb
import structlog

logger = structlog.get_logger()


class LLMAuditLogger:
    """
    Log every LLM call to DuckDB llm_audit table.
    
    Used as a context manager around LLM invocations:
    
        with audit.log_call("BoundaryDetectorAgent", "ollama_8b") as call:
            result = llm_client.generate(prompt)
            call.set_response(result)
    """

    def __init__(self, db_path: str = "analytics.duckdb"):
        self.db_path = db_path

    @contextmanager
    def log_call(
        self,
        agent_name: str,
        model_name: str,
        prompt: str,
        tier: Optional[str] = None,
    ):
        """Context manager for logging an LLM call."""
        call = _LLMCallTracker(
            db_path=self.db_path,
            agent_name=agent_name,
            model_name=model_name,
            prompt=prompt,
            tier=tier,
        )
        call.start()
        try:
            yield call
            call.succeed()
        except Exception as e:
            call.fail(str(e))
            raise
        finally:
            call.persist()


class _LLMCallTracker:
    def __init__(self, db_path, agent_name, model_name, prompt, tier):
        self.db_path = db_path
        self.call_id = str(uuid.uuid4())
        self.agent_name = agent_name
        self.model_name = model_name
        self.prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        self.response_hash = None
        self.latency_ms = 0.0
        self.success = False
        self.error_msg = None
        self.tier = tier
        self._start_time = None

    def start(self):
        self._start_time = time.perf_counter()

    def set_response(self, response_text: str):
        self.response_hash = hashlib.sha256(
            response_text.encode()
        ).hexdigest()[:16]

    def succeed(self):
        self.success = True
        self.latency_ms = (time.perf_counter() - self._start_time) * 1000

    def fail(self, error: str):
        self.success = False
        self.error_msg = error
        self.latency_ms = (time.perf_counter() - self._start_time) * 1000

    def persist(self):
        try:
            con = duckdb.connect(self.db_path)
            con.execute("""
                INSERT INTO llm_audit
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
            """, [
                self.call_id, self.agent_name, self.model_name,
                self.prompt_hash, self.response_hash,
                self.latency_ms, self.success,
                self.error_msg, self.tier,
            ])
            con.close()
        except Exception as e:
            logger.warning("audit_persist_failed", error=str(e))
```

---

### Task 4: PartitionOrchestrator (#15) — LangGraph StateGraph

**File**: `partition/orchestration/orchestrator.py`

```python
import uuid
from typing import Optional
from langgraph.graph import StateGraph, END
import structlog

from partition.orchestration.state import PipelineState, PipelineStage
from partition.orchestration.checkpoint import RedisCheckpointManager
from partition.orchestration.audit import LLMAuditLogger

logger = structlog.get_logger()


class PartitionOrchestrator:
    """
    Agent #15: LangGraph-based orchestrator for the full L2 pipeline.
    
    Coordinates all 11 agents (L2-A through L2-E) in sequence with:
    - CROSS_FILE_RESOLVE state tracking
    - Redis checkpoints every 50 blocks
    - DuckDB audit logging for all LLM calls
    - Error recovery with retry + fallback
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        duckdb_path: str = "analytics.duckdb",
        target_runtime: str = "python",
    ):
        self.checkpoint = RedisCheckpointManager(redis_url)
        self.audit = LLMAuditLogger(duckdb_path)
        self.target_runtime = target_runtime

        # Build the LangGraph StateGraph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Construct the LangGraph pipeline."""
        workflow = StateGraph(PipelineState)

        # Add nodes for each stage
        workflow.add_node("file_scan", self._node_file_scan)
        workflow.add_node("cross_file_resolve", self._node_cross_file_resolve)
        workflow.add_node("streaming", self._node_streaming)
        workflow.add_node("boundary_detection", self._node_boundary)
        workflow.add_node("raptor_clustering", self._node_raptor)
        workflow.add_node("complexity_analysis", self._node_complexity)
        workflow.add_node("strategy_assignment", self._node_strategy)
        workflow.add_node("persistence", self._node_persistence)
        workflow.add_node("indexing", self._node_indexing)

        # Set entry point
        workflow.set_entry_point("file_scan")

        # Define edges (sequential pipeline)
        workflow.add_edge("file_scan", "cross_file_resolve")
        workflow.add_edge("cross_file_resolve", "streaming")
        workflow.add_edge("streaming", "boundary_detection")
        workflow.add_edge("boundary_detection", "raptor_clustering")
        workflow.add_edge("raptor_clustering", "complexity_analysis")
        workflow.add_edge("complexity_analysis", "strategy_assignment")
        workflow.add_edge("strategy_assignment", "persistence")
        workflow.add_edge("persistence", "indexing")
        workflow.add_edge("indexing", END)

        return workflow.compile()

    async def run(self, input_paths: list[str]) -> PipelineState:
        """
        Execute the full L2 pipeline.
        
        Args:
            input_paths: List of SAS file paths to process
            
        Returns:
            Final PipelineState with all results
        """
        run_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())

        initial_state: PipelineState = {
            "input_paths": input_paths,
            "target_runtime": self.target_runtime,
            "stage": PipelineStage.INIT.value,
            "current_file_idx": 0,
            "file_ids": [],
            "cross_file_deps": {},
            "partitions": [],
            "partition_count": 0,
            "raptor_nodes": [],
            "complexity_computed": False,
            "persisted_count": 0,
            "scc_groups": [],
            "max_hop": 3,
            "last_checkpoint_block": 0,
            "checkpoint_key": None,
            "errors": [],
            "warnings": [],
            "trace_id": trace_id,
            "run_id": run_id,
        }

        # Check for existing checkpoints
        for path in input_paths:
            checkpoint = self.checkpoint.find_latest_checkpoint(path)
            if checkpoint:
                logger.info("resuming_from_checkpoint",
                           file=path,
                           block=checkpoint["block_num"])
                initial_state["last_checkpoint_block"] = checkpoint["block_num"]

        logger.info("orchestrator_start",
                     run_id=run_id,
                     n_files=len(input_paths),
                     target=self.target_runtime)

        # Execute the graph
        final_state = await self.graph.ainvoke(initial_state)

        logger.info("orchestrator_complete",
                     run_id=run_id,
                     partitions=final_state["partition_count"],
                     errors=len(final_state["errors"]))

        return final_state

    # --- Node implementations ---

    async def _node_file_scan(self, state: PipelineState) -> dict:
        """L2-A: Scan files, detect encoding, register."""
        from partition.entry.file_analysis_agent import FileAnalysisAgent
        from partition.entry.registry_writer_agent import RegistryWriterAgent

        state["stage"] = PipelineStage.FILE_SCAN.value
        agent = FileAnalysisAgent(trace_id=state["trace_id"])
        writer = RegistryWriterAgent(trace_id=state["trace_id"])

        file_ids = []
        for path in state["input_paths"]:
            try:
                result = await agent.process(path)
                file_id = await writer.process(result)
                file_ids.append(file_id)
            except Exception as e:
                state["errors"].append(f"File scan failed: {path}: {e}")
                logger.error("file_scan_error", path=path, error=str(e))

        return {"file_ids": file_ids, "stage": PipelineStage.FILE_SCAN.value}

    async def _node_cross_file_resolve(self, state: PipelineState) -> dict:
        """L2-A: Resolve cross-file dependencies."""
        from partition.entry.cross_file_resolver import CrossFileDependencyResolver

        state["stage"] = PipelineStage.CROSS_FILE_RESOLVE.value
        resolver = CrossFileDependencyResolver(trace_id=state["trace_id"])

        try:
            deps = await resolver.process(state["input_paths"])
            return {"cross_file_deps": deps,
                    "stage": PipelineStage.CROSS_FILE_RESOLVE.value}
        except Exception as e:
            state["warnings"].append(f"Cross-file resolve partial: {e}")
            return {"cross_file_deps": {},
                    "stage": PipelineStage.CROSS_FILE_RESOLVE.value}

    async def _node_streaming(self, state: PipelineState) -> dict:
        """L2-B: Stream files through StateAgent."""
        from partition.streaming.stream_agent import StreamAgent
        from partition.streaming.state_agent import StateAgent

        state["stage"] = PipelineStage.STREAMING.value
        streamer = StreamAgent(trace_id=state["trace_id"])
        state_agent = StateAgent(trace_id=state["trace_id"])

        all_chunks = []
        for path in state["input_paths"]:
            try:
                async for chunk in streamer.stream(path):
                    enriched = await state_agent.process(chunk)
                    all_chunks.append(enriched)

                    # Checkpoint every 50 blocks
                    block_num = len(all_chunks)
                    if block_num % 50 == 0:
                        self.checkpoint.save_checkpoint(
                            file_id=path,
                            block_num=block_num,
                            partition_data=[{"idx": block_num}],
                        )
            except Exception as e:
                state["errors"].append(f"Streaming failed: {path}: {e}")

        return {"partitions": all_chunks,
                "partition_count": len(all_chunks),
                "stage": PipelineStage.STREAMING.value}

    async def _node_boundary(self, state: PipelineState) -> dict:
        """L2-C: Detect block boundaries."""
        from partition.boundary.boundary_detector_agent import BoundaryDetectorAgent

        state["stage"] = PipelineStage.BOUNDARY_DETECTION.value
        detector = BoundaryDetectorAgent(trace_id=state["trace_id"])

        partitions = []
        for chunk in state["partitions"]:
            try:
                partition = await detector.process(chunk)
                partitions.append(partition)
            except Exception as e:
                state["warnings"].append(f"Boundary detection skip: {e}")

        return {"partitions": partitions,
                "partition_count": len(partitions),
                "stage": PipelineStage.BOUNDARY_DETECTION.value}

    async def _node_raptor(self, state: PipelineState) -> dict:
        """L2-C: RAPTOR semantic clustering."""
        from partition.raptor.raptor_agent import RAPTORPartitionAgent

        state["stage"] = PipelineStage.RAPTOR_CLUSTERING.value
        agent = RAPTORPartitionAgent(trace_id=state["trace_id"])

        # Group partitions by file
        file_groups = {}
        for p in state["partitions"]:
            fid = str(p.source_file_id)
            file_groups.setdefault(fid, []).append(p)

        all_raptor_nodes = []
        for file_id, file_partitions in file_groups.items():
            try:
                nodes = await agent.process(file_partitions, file_id)
                all_raptor_nodes.extend(nodes)
            except Exception as e:
                state["warnings"].append(f"RAPTOR failed for {file_id}: {e}")

        return {"raptor_nodes": all_raptor_nodes,
                "stage": PipelineStage.RAPTOR_CLUSTERING.value}

    async def _node_complexity(self, state: PipelineState) -> dict:
        """L2-D: Compute complexity scores."""
        from partition.complexity.complexity_agent import ComplexityAgent

        state["stage"] = PipelineStage.COMPLEXITY_ANALYSIS.value
        agent = ComplexityAgent(trace_id=state["trace_id"])

        for p in state["partitions"]:
            try:
                await agent.process(p)
            except Exception as e:
                state["warnings"].append(f"Complexity skip: {e}")

        return {"complexity_computed": True,
                "stage": PipelineStage.COMPLEXITY_ANALYSIS.value}

    async def _node_strategy(self, state: PipelineState) -> dict:
        """L2-D: Assign strategies."""
        from partition.complexity.strategy_agent import StrategyAgent

        state["stage"] = PipelineStage.STRATEGY_ASSIGNMENT.value
        agent = StrategyAgent(trace_id=state["trace_id"])

        for p in state["partitions"]:
            try:
                await agent.process(p)
            except Exception as e:
                state["warnings"].append(f"Strategy skip: {e}")

        return {"stage": PipelineStage.STRATEGY_ASSIGNMENT.value}

    async def _node_persistence(self, state: PipelineState) -> dict:
        """L2-E: Persist partitions."""
        from partition.persistence.persistence_agent import PersistenceAgent

        state["stage"] = PipelineStage.PERSISTENCE.value
        agent = PersistenceAgent(trace_id=state["trace_id"])

        count = await agent.process(state["partitions"])

        return {"persisted_count": count,
                "stage": PipelineStage.PERSISTENCE.value}

    async def _node_indexing(self, state: PipelineState) -> dict:
        """L2-E: Build dependency graph."""
        from partition.index.index_agent import IndexAgent
        from partition.index.kuzu_writer import KuzuGraphWriter
        from partition.config.config_manager import ProjectConfigManager

        state["stage"] = PipelineStage.INDEXING.value
        agent = IndexAgent(trace_id=state["trace_id"])

        dag, condensed, scc_groups, max_hop = await agent.process(
            state["partitions"],
            state["cross_file_deps"],
        )

        # Write to Kuzu
        try:
            kuzu_writer = KuzuGraphWriter()
            kuzu_writer.write_partitions(state["partitions"])
            kuzu_writer.write_edges(dag)
        except Exception as e:
            state["warnings"].append(f"Kuzu write failed: {e}")

        # Save hop cap
        config = ProjectConfigManager()
        config.set_max_hop(max_hop)

        # Clear checkpoints for completed files
        for path in state["input_paths"]:
            self.checkpoint.clear_checkpoints(path)

        return {
            "scc_groups": [list(s) for s in scc_groups],
            "max_hop": max_hop,
            "stage": PipelineStage.COMPLETE.value,
        }
```

**Install LangGraph + Redis**:
```bash
pip install langgraph redis
```

---

### Task 5: CLI Entry Point

**File**: `scripts/run_pipeline.py`

```python
import asyncio
import argparse
import structlog
from partition.orchestration.orchestrator import PartitionOrchestrator
from partition.db.duckdb_manager import init_all_duckdb_tables

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
)


def main():
    parser = argparse.ArgumentParser(
        description="SAS → Python/PySpark Partition Pipeline"
    )
    parser.add_argument("files", nargs="+", help="SAS file paths")
    parser.add_argument("--target", choices=["python", "pyspark"],
                       default="python", help="Target runtime")
    parser.add_argument("--redis", default="redis://localhost:6379/0",
                       help="Redis URL for checkpointing")
    parser.add_argument("--duckdb", default="analytics.duckdb",
                       help="DuckDB path for audit logs")
    args = parser.parse_args()

    # Initialize analytics DB
    init_all_duckdb_tables(args.duckdb)

    # Create and run orchestrator
    orchestrator = PartitionOrchestrator(
        redis_url=args.redis,
        duckdb_path=args.duckdb,
        target_runtime=args.target,
    )

    result = asyncio.run(orchestrator.run(args.files))

    print(f"\n{'='*60}")
    print(f"Pipeline Complete")
    print(f"  Files processed: {len(result['input_paths'])}")
    print(f"  Partitions: {result['partition_count']}")
    print(f"  Persisted: {result['persisted_count']}")
    print(f"  SCC groups: {len(result['scc_groups'])}")
    print(f"  Max hop: {result['max_hop']}")
    print(f"  Errors: {len(result['errors'])}")
    print(f"  Warnings: {len(result['warnings'])}")
    print(f"{'='*60}")

    if result['errors']:
        print("\nErrors:")
        for e in result['errors']:
            print(f"  ✗ {e}")

    if result['warnings']:
        print("\nWarnings:")
        for w in result['warnings'][:10]:
            print(f"  ⚠ {w}")


if __name__ == "__main__":
    main()
```

**Usage**:
```bash
python scripts/run_pipeline.py data/sas_files/*.sas --target python
python scripts/run_pipeline.py data/sas_files/*.sas --target pyspark --redis redis://localhost:6379/1
```

---

### Task 6: Tests

**File**: `tests/test_orchestration.py`

```python
import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock


class TestRedisCheckpoint:
    def test_degraded_mode(self):
        """Pipeline works without Redis (degraded mode)."""
        from partition.orchestration.checkpoint import RedisCheckpointManager
        # Connect to a non-existent Redis
        mgr = RedisCheckpointManager("redis://localhost:99999")
        assert mgr.available is False
        assert mgr.save_checkpoint("f1", 50, []) is False
        assert mgr.find_latest_checkpoint("f1") is None

    def test_checkpoint_interval(self):
        """Checkpoints only save every 50 blocks."""
        from partition.orchestration.checkpoint import RedisCheckpointManager
        mgr = RedisCheckpointManager.__new__(RedisCheckpointManager)
        mgr.available = True
        mgr.client = MagicMock()
        # Block 25 should NOT checkpoint
        result = mgr.save_checkpoint("f1", 25, [])
        assert result is False

    @pytest.mark.skipif(
        not _redis_available(), reason="Redis not running"
    )
    def test_save_and_find(self):
        """Save checkpoint, then find it."""
        from partition.orchestration.checkpoint import RedisCheckpointManager
        mgr = RedisCheckpointManager()
        if not mgr.available:
            pytest.skip("Redis not available")
        mgr.save_checkpoint("test_file", 0, [{"test": True}])
        checkpoint = mgr.find_latest_checkpoint("test_file")
        assert checkpoint is not None
        assert checkpoint["file_id"] == "test_file"
        mgr.clear_checkpoints("test_file")


class TestLLMAuditLogger:
    def test_audit_context_manager(self, tmp_path):
        """Audit logs an LLM call."""
        from partition.orchestration.audit import LLMAuditLogger
        from partition.db.duckdb_manager import init_all_duckdb_tables
        import duckdb

        db_path = str(tmp_path / "test_audit.duckdb")
        init_all_duckdb_tables(db_path)
        audit = LLMAuditLogger(db_path)

        with audit.log_call("TestAgent", "test_model", "test prompt") as call:
            call.set_response("test response")

        con = duckdb.connect(db_path)
        rows = con.execute("SELECT * FROM llm_audit").fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "TestAgent"  # agent_name
        assert rows[0][6] is True          # success
        con.close()


class TestPipelineState:
    def test_state_has_all_fields(self):
        """PipelineState must have all required fields."""
        from partition.orchestration.state import PipelineState
        required = ["input_paths", "stage", "partitions",
                     "file_ids", "cross_file_deps", "errors"]
        for field in required:
            assert field in PipelineState.__annotations__


class TestOrchestratorGraph:
    def test_graph_compiles(self):
        """The LangGraph StateGraph should compile without errors."""
        from partition.orchestration.orchestrator import PartitionOrchestrator
        # Don't need actual Redis for graph compilation
        with patch('partition.orchestration.checkpoint.RedisCheckpointManager'):
            orchestrator = PartitionOrchestrator.__new__(PartitionOrchestrator)
            orchestrator.checkpoint = MagicMock()
            orchestrator.audit = MagicMock()
            orchestrator.target_runtime = "python"
            graph = orchestrator._build_graph()
            assert graph is not None


def _redis_available():
    try:
        import redis
        r = redis.from_url("redis://localhost:6379/0")
        r.ping()
        return True
    except Exception:
        return False
```

---

## Checklist — End of Week 8

- [ ] `partition/orchestration/state.py` — PipelineState + PipelineStage enum
- [ ] `partition/orchestration/checkpoint.py` — Redis checkpoint with TTL + degraded mode
- [ ] `partition/orchestration/audit.py` — LLM audit logger to DuckDB
- [ ] `partition/orchestration/orchestrator.py` — PartitionOrchestrator (#15) LangGraph
- [ ] `scripts/run_pipeline.py` — CLI entry point
- [ ] Full L2 pipeline runs end-to-end (file scan → indexing)
- [ ] Redis checkpoint saves every 50 blocks
- [ ] Pipeline resumes from checkpoint after simulated crash
- [ ] Pipeline completes without Redis (degraded mode)
- [ ] Every LLM call logged to `llm_audit` DuckDB table
- [ ] CROSS_FILE_RESOLVE state flows through pipeline
- [ ] Error recovery: individual agent failures don't crash pipeline
- [ ] `tests/test_orchestration.py` — ≥ 8 assertions
- [ ] E2E smoke test: `tests/test_e2e_smoke.py` on 10 SAS files
- [ ] Git: `week-08` branch, merged to `main`

---

## Evaluation Metrics for This Week

| Metric | Target | How to Measure |
|--------|--------|----------------|
| E2E pipeline success rate | ≥ 90% of files | 10-file smoke test |
| Checkpoint resume correctness | Exact block count | Crash simulation |
| Redis degraded mode | Pipeline completes | Disable Redis, run pipeline |
| LLM audit completeness | Every LLM call logged | Count `llm_audit` rows vs expected calls |
| Pipeline latency (10 files) | < 60 s | `time python scripts/run_pipeline.py` |
| Error isolation | 1 bad file doesn't crash others | Inject 1 corrupt file in 10-file batch |

---

## Dependencies Added This Week

| Package | Version | Purpose |
|---------|---------|---------|
| langgraph | ≥ 0.1 | StateGraph orchestration |
| redis | ≥ 5.0 | Checkpoint persistence |
| structlog | ≥ 23.1 | JSON structured logging |

---

> *Week 8 Complete → You have: 16 agents, full L2 pipeline orchestrated with LangGraph, Redis checkpointing, DuckDB audit logging. P1 phase is done! Next: Robustness + KB Generation (Week 9, P2).*
