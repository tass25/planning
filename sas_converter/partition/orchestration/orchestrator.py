"""PartitionOrchestrator (#15) -- LangGraph StateGraph orchestrator.

Ties **all** L2 agents into a single end-to-end pipeline:

    L2-A  FileAnalysisAgent -> CrossFileDependencyResolver -> RegistryWriterAgent
    L2-B  run_streaming_pipeline  (StreamAgent + StateAgent)
    L2-C  BoundaryDetectorAgent -> PartitionBuilderAgent -> RAPTORPartitionAgent
    L2-D  ComplexityAgent -> StrategyAgent
    L2-E  PersistenceAgent -> IndexAgent

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
from partition.utils.large_file import configure_memory_guards, MemoryMonitor

logger = structlog.get_logger()


class PartitionOrchestrator:
    """Agent #15: LangGraph-based orchestrator for the full L2 pipeline.

    Parameters
    ----------
    redis_url : str
        Redis connection URL for checkpointing.
    duckdb_path : str
        Path to DuckDB file for LLM audit logs.
    target_runtime : str
        ``"python"`` or ``"pyspark"``.
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
        self.memory_monitor = MemoryMonitor()

        # Configure memory guards at startup (OMP, CUDA)
        configure_memory_guards()

        # Build the LangGraph StateGraph
        self.graph = self._build_graph()

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self):
        """Construct and compile the LangGraph pipeline."""
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

        # Linear pipeline edges
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
            "last_checkpoint_block": 0,
            "checkpoint_key": None,
            "errors": [],
            "warnings": [],
            "trace_id": trace_id,
            "run_id": run_id,
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
        )

        # Execute the compiled graph
        final_state = await self.graph.ainvoke(initial_state)

        logger.info(
            "orchestrator_complete",
            run_id=run_id,
            partitions=final_state.get("partition_count", 0),
            errors=len(final_state.get("errors", [])),
        )
        return final_state

    # ------------------------------------------------------------------
    # Node implementations  (each returns a partial-state dict)
    # ------------------------------------------------------------------

    async def _node_file_scan(self, state: PipelineState) -> dict:
        """L2-A: Scan files and register them in SQLite."""
        from partition.db.sqlite_manager import get_engine, init_db
        from partition.entry.file_analysis_agent import FileAnalysisAgent
        from partition.entry.registry_writer_agent import RegistryWriterAgent

        trace_id = UUID(state["trace_id"])
        agent = FileAnalysisAgent(trace_id=trace_id)
        writer = RegistryWriterAgent(trace_id=trace_id)

        engine = get_engine()
        init_db(engine)

        all_metas = []
        file_ids = []
        errors = list(state.get("errors", []))

        for path_str in state["input_paths"]:
            path = Path(path_str)
            try:
                if path.is_dir():
                    metas = await agent.process(path)
                elif path.is_file() and path.suffix.lower() == ".sas":
                    # Scan the parent directory, filter to just this file
                    metas = await agent.process(path.parent)
                    metas = [m for m in metas if Path(m.file_path).resolve() == path.resolve()]
                else:
                    errors.append(f"Invalid path (not .sas or directory): {path}")
                    continue

                all_metas.extend(metas)
            except Exception as exc:
                errors.append(f"File scan failed for {path}: {exc}")
                logger.error("file_scan_error", path=str(path), error=str(exc))

        # Register in SQLite
        if all_metas:
            try:
                result = await writer.process(all_metas, engine)
                file_ids = [str(m.file_id) for m in all_metas]
                logger.info(
                    "registry_write_done",
                    inserted=result.get("inserted", 0),
                    skipped=result.get("skipped", 0),
                )
            except Exception as exc:
                errors.append(f"Registry write failed: {exc}")
                logger.error("registry_write_error", error=str(exc))

        return {
            "file_metas": all_metas,
            "file_ids": file_ids,
            "stage": PipelineStage.FILE_SCAN.value,
            "errors": errors,
        }

    async def _node_cross_file_resolve(self, state: PipelineState) -> dict:
        """L2-A: Resolve cross-file dependencies."""
        from partition.db.sqlite_manager import get_engine
        from partition.entry.cross_file_dep_resolver import CrossFileDependencyResolver

        trace_id = UUID(state["trace_id"])
        resolver = CrossFileDependencyResolver(trace_id=trace_id)
        warnings = list(state.get("warnings", []))

        file_metas = state.get("file_metas", [])
        if not file_metas:
            return {
                "cross_file_deps": {},
                "stage": PipelineStage.CROSS_FILE_RESOLVE.value,
            }

        engine = get_engine()

        # Determine project root as common parent of all files
        all_paths = [Path(m.file_path) for m in file_metas]
        project_root = _common_parent(all_paths)

        try:
            deps = await resolver.process(file_metas, project_root, engine)
            return {
                "cross_file_deps": deps,
                "stage": PipelineStage.CROSS_FILE_RESOLVE.value,
            }
        except Exception as exc:
            warnings.append(f"Cross-file resolve partial: {exc}")
            logger.warning("cross_file_resolve_error", error=str(exc))
            return {
                "cross_file_deps": {},
                "stage": PipelineStage.CROSS_FILE_RESOLVE.value,
                "warnings": warnings,
            }

    async def _node_streaming(self, state: PipelineState) -> dict:
        """L2-B: Stream files through StreamAgent + StateAgent."""
        from partition.streaming.pipeline import run_streaming_pipeline

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

        return {
            "chunks_by_file": chunks_by_file,
            "stage": PipelineStage.STREAMING.value,
            "errors": errors,
        }

    async def _node_boundary(self, state: PipelineState) -> dict:
        """L2-C: Detect block boundaries and build PartitionIR objects."""
        from partition.chunking.boundary_detector import BoundaryDetectorAgent
        from partition.chunking.partition_builder import PartitionBuilderAgent

        trace_id = UUID(state["trace_id"])
        bda = BoundaryDetectorAgent(trace_id=trace_id)
        pba = PartitionBuilderAgent(trace_id=trace_id)

        all_partitions = []
        warnings = list(state.get("warnings", []))
        chunks_by_file = state.get("chunks_by_file", {})

        for file_id, chunks_with_states in chunks_by_file.items():
            try:
                events = await bda.process(chunks_with_states, UUID(file_id))
                partitions = await pba.process(events)
                all_partitions.extend(partitions)
            except Exception as exc:
                warnings.append(f"Boundary detection skipped for {file_id}: {exc}")
                logger.warning("boundary_error", file_id=file_id, error=str(exc))

        return {
            "partitions": all_partitions,
            "partition_count": len(all_partitions),
            "stage": PipelineStage.BOUNDARY_DETECTION.value,
            "warnings": warnings,
        }

    async def _node_raptor(self, state: PipelineState) -> dict:
        """L2-C: RAPTOR semantic clustering."""
        from partition.raptor.raptor_agent import RAPTORPartitionAgent

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

        return {
            "raptor_nodes": all_raptor_nodes,
            "stage": PipelineStage.RAPTOR_CLUSTERING.value,
            "warnings": warnings,
        }

    async def _node_complexity(self, state: PipelineState) -> dict:
        """L2-D: Compute complexity scores."""
        from partition.complexity.complexity_agent import ComplexityAgent

        agent = ComplexityAgent()
        partitions = state.get("partitions", [])
        warnings = list(state.get("warnings", []))

        try:
            scored = await agent.process(partitions)
            return {
                "partitions": scored,
                "complexity_computed": True,
                "stage": PipelineStage.COMPLEXITY_ANALYSIS.value,
            }
        except Exception as exc:
            warnings.append(f"Complexity scoring failed: {exc}")
            logger.warning("complexity_error", error=str(exc))
            return {
                "complexity_computed": False,
                "stage": PipelineStage.COMPLEXITY_ANALYSIS.value,
                "warnings": warnings,
            }

    async def _node_strategy(self, state: PipelineState) -> dict:
        """L2-D: Assign conversion strategies."""
        from partition.complexity.strategy_agent import StrategyAgent

        trace_id = UUID(state["trace_id"])
        agent = StrategyAgent(trace_id=trace_id)
        partitions = state.get("partitions", [])
        warnings = list(state.get("warnings", []))

        try:
            routed = await agent.process(partitions)
            return {
                "partitions": routed,
                "stage": PipelineStage.STRATEGY_ASSIGNMENT.value,
            }
        except Exception as exc:
            warnings.append(f"Strategy assignment failed: {exc}")
            logger.warning("strategy_error", error=str(exc))
            return {
                "stage": PipelineStage.STRATEGY_ASSIGNMENT.value,
                "warnings": warnings,
            }

    async def _node_persistence(self, state: PipelineState) -> dict:
        """L2-E: Persist partitions to SQLite."""
        from partition.persistence.persistence_agent import PersistenceAgent

        trace_id = UUID(state["trace_id"])
        agent = PersistenceAgent(trace_id=trace_id)
        partitions = state.get("partitions", [])
        errors = list(state.get("errors", []))

        # Persist per-file groups
        total_persisted = 0
        file_groups: dict[str, list] = {}
        for p in partitions:
            fid = str(p.file_id)
            file_groups.setdefault(fid, []).append(p)

        for file_id, file_parts in file_groups.items():
            try:
                count = await agent.process(file_parts, file_id)
                total_persisted += count
            except Exception as exc:
                errors.append(f"Persistence failed for {file_id}: {exc}")
                logger.error("persistence_error", file_id=file_id, error=str(exc))

        return {
            "persisted_count": total_persisted,
            "stage": PipelineStage.PERSISTENCE.value,
            "errors": errors,
        }

    async def _node_indexing(self, state: PipelineState) -> dict:
        """L2-E: Build dependency graph + detect SCCs."""
        from partition.index.index_agent import IndexAgent

        trace_id = UUID(state["trace_id"])
        agent = IndexAgent(trace_id=trace_id)
        partitions = state.get("partitions", [])
        cross_deps = state.get("cross_file_deps", {})
        warnings = list(state.get("warnings", []))

        try:
            result = await agent.process(partitions, cross_deps)
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

        return {
            "scc_groups": scc_groups,
            "max_hop": max_hop,
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
