"""PartitionOrchestrator (#15) -- LangGraph StateGraph orchestrator.

Consolidated 8-node pipeline (was 11):

    1. file_process    FileProcessor  (scan + registry + cross-file deps)
    2. streaming       StreamingParser
    3. chunking        ChunkingAgent  (boundary + partition builder)
    4. raptor          RAPTORPartitionAgent
    5. risk_routing    RiskRouter     (complexity + strategy)
    6. persist_index   PersistenceAgent + IndexAgent  (utility step)
    7. translation     TranslationPipeline (translate + validate + retry)
    8. merge           MergeAgent     (assemble final scripts + reports)

Features:
    * Redis checkpointing every 50 blocks (degraded mode if Redis unavailable)
    * DuckDB LLM audit logging for every external call
    * Error isolation -- one agent failure does not crash the pipeline
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional
from uuid import UUID

import structlog
from langgraph.graph import END, StateGraph

from partition.orchestration.audit import LLMAuditLogger
from partition.orchestration.checkpoint import RedisCheckpointManager
from partition.orchestration.state import PipelineStage, PipelineState
from partition.orchestration.telemetry import track_event, track_metric, trace_span
from partition.utils.large_file import configure_memory_guards, MemoryMonitor

logger = structlog.get_logger()

# Bump this whenever the pipeline graph topology or node semantics change.
PIPELINE_VERSION = "3.0.0"


class PartitionOrchestrator:
    """Agent #15: LangGraph-based orchestrator for the full L2 pipeline.

    Parameters
    ----------
    redis_url : str
        Redis connection URL for checkpointing.
    duckdb_path : str
        Path to DuckDB file for LLM audit logs.
    target_runtime : str
        ``"python"``.
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
        self.duckdb_path = duckdb_path

        # Memory monitoring (best-effort — system deps may be unavailable)
        try:
            self.memory_monitor = MemoryMonitor()
        except Exception as exc:
            logger.warning("memory_monitor_init_failed", error=str(exc))
            self.memory_monitor = None

        # Agent cache — avoid re-instantiation per node call
        self._agents: dict[str, object] = {}

        # Configure memory guards at startup (OMP, CUDA) — best-effort
        try:
            configure_memory_guards()
        except Exception as exc:
            logger.warning("memory_guards_failed", error=str(exc))

        # Build the LangGraph StateGraph
        self.graph = self._build_graph()

    # ------------------------------------------------------------------
    # Agent cache helper
    # ------------------------------------------------------------------

    def _get_agent(self, key: str, factory):
        """Return a cached agent instance, creating it on first call."""
        if key not in self._agents:
            self._agents[key] = factory()
        return self._agents[key]

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self):
        """Construct and compile the consolidated 8-node LangGraph pipeline."""
        workflow = StateGraph(PipelineState)

        # Consolidated nodes (was 11, now 8)
        workflow.add_node("file_process", self._node_file_process)
        workflow.add_node("streaming", self._node_streaming)
        workflow.add_node("chunking", self._node_chunking)
        workflow.add_node("raptor", self._node_raptor)
        workflow.add_node("risk_routing", self._node_risk_routing)
        workflow.add_node("persist_index", self._node_persist_index)
        workflow.add_node("translation", self._node_translation)
        workflow.add_node("merge", self._node_merge)

        # Set entry point
        workflow.set_entry_point("file_process")

        # Linear pipeline edges
        workflow.add_edge("file_process", "streaming")
        workflow.add_edge("streaming", "chunking")
        workflow.add_edge("chunking", "raptor")
        workflow.add_edge("raptor", "risk_routing")
        workflow.add_edge("risk_routing", "persist_index")
        workflow.add_edge("persist_index", "translation")
        workflow.add_edge("translation", "merge")
        workflow.add_edge("merge", END)

        return workflow.compile()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, input_paths: list[str]) -> PipelineState:
        """Execute the full L2 pipeline.

        Parameters
        ----------
        input_paths : list[str]
            SAS file paths **or** directories to process.

        Returns
        -------
        PipelineState
            Final state with all results.
        """
        run_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())

        initial_state: PipelineState = {
            "input_paths": input_paths,
            "target_runtime": self.target_runtime,
            "stage": PipelineStage.INIT.value,
            "current_file_idx": 0,
            "file_metas": [],
            "file_ids": [],
            "cross_file_deps": {},
            "chunks_by_file": {},
            "partitions": [],
            "partition_count": 0,
            "raptor_nodes": [],
            "complexity_computed": False,
            "persisted_count": 0,
            "scc_groups": [],
            "max_hop": 3,
            "conversion_results": [],
            "validation_passed": 0,
            "merge_results": [],
            "last_checkpoint_block": 0,
            "checkpoint_key": None,
            "errors": [],
            "warnings": [],
            "trace_id": trace_id,
            "run_id": run_id,
            "pipeline_version": PIPELINE_VERSION,
        }

        # Check for existing checkpoints
        for path in input_paths:
            cp = self.checkpoint.find_latest_checkpoint(path)
            if cp:
                logger.info(
                    "resuming_from_checkpoint",
                    file=path,
                    block=cp["block_num"],
                )
                initial_state["last_checkpoint_block"] = cp["block_num"]

        logger.info(
            "orchestrator_start",
            run_id=run_id,
            n_files=len(input_paths),
            target=self.target_runtime,
            pipeline_version=PIPELINE_VERSION,
        )

        # Execute the compiled graph
        with trace_span("pipeline_run", {"run_id": run_id, "n_files": str(len(input_paths))}):
            final_state = await self.graph.ainvoke(initial_state)

        n_errors = len(final_state.get("errors", []))
        n_parts = final_state.get("partition_count", 0)
        track_event("pipeline_complete", {
            "run_id": run_id,
            "partitions": str(n_parts),
            "errors": str(n_errors),
            "pipeline_version": PIPELINE_VERSION,
        })
        track_metric("pipeline_partition_count", float(n_parts), {"run_id": run_id})

        logger.info(
            "orchestrator_complete",
            run_id=run_id,
            partitions=n_parts,
            errors=n_errors,
        )
        return final_state

    # ------------------------------------------------------------------
    # Node implementations  (each returns a partial-state dict)
    # ------------------------------------------------------------------

    async def _node_file_process(self, state: PipelineState) -> dict:
        """Consolidated L2-A: Scan, register, and resolve cross-file deps."""
        import time as _t
        from partition.entry.file_processor import FileProcessor
        _t0 = _t.perf_counter()

        trace_id = UUID(state["trace_id"])
        agent = self._get_agent("file_processor", lambda: FileProcessor(trace_id=trace_id))
        errors = list(state.get("errors", []))
        warnings = list(state.get("warnings", []))

        try:
            file_metas, cross_deps = await agent.process(
                state["input_paths"],
                engine=None,  # FileProcessor creates its own engine
            )
            file_ids = [str(m.file_id) for m in file_metas]
        except Exception as exc:
            # L2-A failure is fatal — downstream stages need file metadata
            logger.error("file_process_fatal", error=str(exc))
            raise RuntimeError(f"L2-A file processing failed (fatal): {exc}") from exc

        track_event("stage_complete", {"stage": "file_process", "files": str(len(file_metas))})
        track_metric("stage_duration_ms", (_t.perf_counter() - _t0) * 1000, {"stage": "file_process"})
        return {
            "file_metas": file_metas,
            "file_ids": file_ids,
            "cross_file_deps": cross_deps,
            "stage": PipelineStage.FILE_SCAN.value,
            "errors": errors,
            "warnings": warnings,
        }

    async def _node_streaming(self, state: PipelineState) -> dict:
        """L2-B: Stream files through StreamAgent + StateAgent."""
        import time as _t
        from partition.streaming.pipeline import run_streaming_pipeline
        _t0 = _t.perf_counter()

        trace_id = UUID(state["trace_id"])
        file_metas = state.get("file_metas", [])
        errors = list(state.get("errors", []))
        chunks_by_file: dict = {}

        for fm in file_metas:
            try:
                chunks = await run_streaming_pipeline(fm, trace_id=trace_id)
                chunks_by_file[str(fm.file_id)] = chunks

                # Checkpoint every 50 blocks
                block_count = sum(len(v) for v in chunks_by_file.values())
                if block_count % 50 == 0 and block_count > 0:
                    self.checkpoint.save_checkpoint(
                        file_id=str(fm.file_id),
                        block_num=block_count,
                        partition_data=[{"idx": block_count}],
                    )
            except Exception as exc:
                errors.append(f"Streaming failed for {fm.file_path}: {exc}")
                logger.error("streaming_error", file=fm.file_path, error=str(exc))

        track_event("stage_complete", {"stage": "streaming", "files": str(len(chunks_by_file))})
        track_metric("stage_duration_ms", (_t.perf_counter() - _t0) * 1000, {"stage": "streaming"})
        return {
            "chunks_by_file": chunks_by_file,
            "stage": PipelineStage.STREAMING.value,
            "errors": errors,
        }

    async def _node_chunking(self, state: PipelineState) -> dict:
        """Consolidated L2-C: Detect boundaries and build PartitionIR objects."""
        import time as _t
        from partition.chunking.chunking_agent import ChunkingAgent
        _t0 = _t.perf_counter()

        trace_id = UUID(state["trace_id"])
        agent = self._get_agent("chunking", lambda: ChunkingAgent(trace_id=trace_id))

        all_partitions = []
        warnings = list(state.get("warnings", []))
        chunks_by_file = state.get("chunks_by_file", {})

        for file_id, chunks_with_states in chunks_by_file.items():
            try:
                partitions = await agent.process(chunks_with_states, UUID(file_id))
                all_partitions.extend(partitions)
            except Exception as exc:
                warnings.append(f"Chunking skipped for {file_id}: {exc}")
                logger.warning("chunking_error", file_id=file_id, error=str(exc))

        track_event("stage_complete", {"stage": "chunking", "partitions": str(len(all_partitions))})
        track_metric("stage_duration_ms", (_t.perf_counter() - _t0) * 1000, {"stage": "chunking"})
        return {
            "partitions": all_partitions,
            "partition_count": len(all_partitions),
            "stage": PipelineStage.BOUNDARY_DETECTION.value,
            "warnings": warnings,
        }

    async def _node_raptor(self, state: PipelineState) -> dict:
        """L2-C: RAPTOR semantic clustering."""
        import time as _t
        from partition.raptor.raptor_agent import RAPTORPartitionAgent
        _t0 = _t.perf_counter()

        trace_id = UUID(state["trace_id"])
        agent = RAPTORPartitionAgent(trace_id=trace_id)

        # Group partitions by file_id
        file_groups: dict[str, list] = {}
        for p in state.get("partitions", []):
            fid = str(p.file_id)
            file_groups.setdefault(fid, []).append(p)

        all_raptor_nodes = []
        warnings = list(state.get("warnings", []))

        for file_id, file_partitions in file_groups.items():
            try:
                nodes = await agent.process(file_partitions, file_id)
                all_raptor_nodes.extend(nodes)
            except Exception as exc:
                warnings.append(f"RAPTOR failed for {file_id}: {exc}")
                logger.warning("raptor_error", file_id=file_id, error=str(exc))

        track_event("stage_complete", {"stage": "raptor", "nodes": str(len(all_raptor_nodes))})
        track_metric("stage_duration_ms", (_t.perf_counter() - _t0) * 1000, {"stage": "raptor"})
        return {
            "raptor_nodes": all_raptor_nodes,
            "stage": PipelineStage.RAPTOR_CLUSTERING.value,
            "warnings": warnings,
        }

    async def _node_risk_routing(self, state: PipelineState) -> dict:
        """Consolidated L2-D: Compute complexity scores and assign strategies."""
        import time as _t
        from partition.complexity.risk_router import RiskRouter
        _t0 = _t.perf_counter()

        agent = self._get_agent("risk_router", RiskRouter)
        partitions = state.get("partitions", [])
        warnings = list(state.get("warnings", []))

        try:
            routed = await agent.process(partitions)
            track_event("stage_complete", {"stage": "risk_routing", "partitions": str(len(routed))})
            track_metric("stage_duration_ms", (_t.perf_counter() - _t0) * 1000, {"stage": "risk_routing"})
            return {
                "partitions": routed,
                "complexity_computed": True,
                "stage": PipelineStage.COMPLEXITY_ANALYSIS.value,
            }
        except Exception as exc:
            warnings.append(f"Risk routing failed: {exc}")
            logger.warning("risk_routing_error", error=str(exc))
            return {
                "complexity_computed": False,
                "stage": PipelineStage.COMPLEXITY_ANALYSIS.value,
                "warnings": warnings,
            }

    async def _node_persist_index(self, state: PipelineState) -> dict:
        """Consolidated L2-E: Persist to SQLite + build dependency DAG."""
        import time as _t
        from partition.persistence.persistence_agent import PersistenceAgent
        from partition.index.index_agent import IndexAgent
        _t0 = _t.perf_counter()

        trace_id = UUID(state["trace_id"])
        persist_agent = self._get_agent(
            "persistence", lambda: PersistenceAgent(trace_id=trace_id)
        )
        index_agent = self._get_agent(
            "index", lambda: IndexAgent(trace_id=trace_id)
        )
        partitions = state.get("partitions", [])
        cross_deps = state.get("cross_file_deps", {})
        errors = list(state.get("errors", []))
        warnings = list(state.get("warnings", []))

        # --- Persist ---
        total_persisted = 0
        file_groups: dict[str, list] = {}
        for p in partitions:
            fid = str(p.file_id)
            file_groups.setdefault(fid, []).append(p)

        for file_id, file_parts in file_groups.items():
            try:
                count = await persist_agent.process(file_parts, file_id)
                total_persisted += count
            except Exception as exc:
                errors.append(f"Persistence failed for {file_id}: {exc}")
                logger.error("persistence_error", file_id=file_id, error=str(exc))

        # --- Index ---
        try:
            result = await index_agent.process(partitions, cross_deps)
            scc_groups = [list(s) for s in result.get("sccs", [])]
            max_hop = result.get("hop_cap", 3)
        except Exception as exc:
            warnings.append(f"Indexing failed: {exc}")
            logger.warning("indexing_error", error=str(exc))
            scc_groups = []
            max_hop = 3

        # Clear checkpoints for completed files
        for fid in state.get("file_ids", []):
            self.checkpoint.clear_checkpoints(fid)

        track_event("stage_complete", {"stage": "persist_index", "persisted": str(total_persisted), "sccs": str(len(scc_groups))})
        track_metric("stage_duration_ms", (_t.perf_counter() - _t0) * 1000, {"stage": "persist_index"})
        return {
            "persisted_count": total_persisted,
            "scc_groups": scc_groups,
            "max_hop": max_hop,
            "stage": PipelineStage.PERSISTENCE.value,
            "errors": errors,
            "warnings": warnings,
        }

    async def _node_translation(self, state: PipelineState) -> dict:
        """Consolidated L3: Translate + validate via TranslationPipeline."""
        import time as _t
        from partition.translation.translation_pipeline import TranslationPipeline
        _t0 = _t.perf_counter()

        pipeline = self._get_agent(
            "translation",
            lambda: TranslationPipeline(
                target_runtime=state.get("target_runtime", "python"),
            ),
        )
        partitions = state.get("partitions", [])
        warnings = list(state.get("warnings", []))
        conversion_results = []
        passed = 0

        for p in partitions:
            try:
                result = await pipeline.translate_partition(p)
                if result is None:
                    warnings.append(f"Translation returned None for {p.block_id}")
                    continue
                conversion_results.append(result)
                if getattr(result, "validation_passed", False):
                    passed += 1
            except Exception as exc:
                warnings.append(f"Translation failed for {p.block_id}: {exc}")
                logger.warning("translation_error", block_id=str(p.block_id), error=str(exc))

        logger.info(
            "translation_complete",
            total=len(partitions),
            translated=len(conversion_results),
            validated=passed,
        )
        track_event("stage_complete", {"stage": "translation", "translated": str(len(conversion_results)), "validated": str(passed)})
        track_metric("stage_duration_ms", (_t.perf_counter() - _t0) * 1000, {"stage": "translation"})
        return {
            "conversion_results": conversion_results,
            "validation_passed": passed,
            "stage": PipelineStage.TRANSLATION.value,
            "warnings": warnings,
        }

    async def _node_merge(self, state: PipelineState) -> dict:
        """Consolidated L4: Merge translated partitions into final scripts."""
        import time as _t
        from partition.merge.merge_agent import MergeAgent
        _t0 = _t.perf_counter()

        agent = self._get_agent("merge", MergeAgent)
        conversion_results = state.get("conversion_results", [])
        partitions = state.get("partitions", [])
        target_runtime = state.get("target_runtime", "python")
        cross_deps = state.get("cross_file_deps", {})
        warnings = list(state.get("warnings", []))

        # Group partitions and conversions by file_id
        partitions_by_file: dict[str, list] = {}
        for p in partitions:
            fid = str(p.file_id)
            partitions_by_file.setdefault(fid, []).append(p)

        conversions_by_file: dict[str, list] = {}
        for cr in conversion_results:
            try:
                fid = str(cr.file_id) if hasattr(cr, "file_id") else str(cr.get("file_id", ""))
            except Exception:
                fid = ""
            if fid:
                conversions_by_file.setdefault(fid, []).append(cr)

        merge_results = []
        for file_id, file_parts in partitions_by_file.items():
            file_conversions = conversions_by_file.get(file_id, [])
            if not file_conversions:
                continue

            # Find source path from file_metas
            source_path = file_id
            for fm in state.get("file_metas", []):
                if str(fm.file_id) == file_id:
                    source_path = fm.file_path
                    break

            try:
                result = await agent.process(
                    conversion_results=[
                        cr.model_dump() if hasattr(cr, "model_dump") else dict(cr)
                        for cr in file_conversions
                    ],
                    partitions=[
                        {
                            "partition_type": getattr(p.partition_type, "value", str(p.partition_type)),
                            "line_start": getattr(p, "line_start", 0),
                            "line_end": getattr(p, "line_end", 0),
                            "raw_code": getattr(p, "raw_code", ""),
                            "source_code": getattr(p, "source_code", ""),
                        }
                        for p in file_parts
                    ],
                    source_file_id=file_id,
                    source_path=source_path,
                    target_runtime=target_runtime,
                )
                merge_results.append(result)
            except Exception as exc:
                warnings.append(f"Merge failed for {file_id}: {exc}")
                logger.warning("merge_error", file_id=file_id, error=str(exc))

        logger.info(
            "merge_complete",
            files_merged=len(merge_results),
            total_files=len(partitions_by_file),
        )
        track_event("stage_complete", {"stage": "merge", "files_merged": str(len(merge_results))})
        track_metric("stage_duration_ms", (_t.perf_counter() - _t0) * 1000, {"stage": "merge"})
        return {
            "merge_results": merge_results,
            "stage": PipelineStage.COMPLETE.value,
            "warnings": warnings,
        }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _common_parent(paths: list[Path]) -> Path:
    """Return the deepest common parent directory of *paths*."""
    if not paths:
        return Path(".")
    resolved = [p.resolve() for p in paths]
    parts_lists = [list(p.parts) for p in resolved]
    common = []
    for parts in zip(*parts_lists):
        if len(set(parts)) == 1:
            common.append(parts[0])
        else:
            break
    if not common:
        return Path(".")
    return Path(*common) if len(common) > 1 else Path(common[0])
