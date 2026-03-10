"""LangGraph state definitions for the partition pipeline.

Defines PipelineStage enum, PipelineState TypedDict
that flows through every node in the LangGraph StateGraph,
and PipelineStateValidator for runtime validation of state snapshots.

Consolidated pipeline (v3.0):
    file_process → streaming → chunking → raptor →
    risk_routing → persist_index → translation → END
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, TypedDict

from pydantic import BaseModel, Field, field_validator


class PipelineStage(str, Enum):
    """Stages in the L2 partition pipeline."""

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
    TRANSLATION = "TRANSLATION"
    VALIDATION = "VALIDATION"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


class PipelineState(TypedDict):
    """LangGraph state object flowing through the pipeline.

    Every node receives this dict and returns a partial update dict
    that is merged back into the state by LangGraph.
    """

    # ---- Input ----
    input_paths: list[str]           # SAS file paths to process
    target_runtime: str              # "python" | "pyspark"

    # ---- Current stage ----
    stage: str                       # PipelineStage value
    current_file_idx: int            # Index into input_paths

    # ---- L2-A outputs ----
    file_metas: list                 # list[FileMetadata] objects
    file_ids: list[str]              # UUIDs from FileRegistry
    cross_file_deps: dict            # {ref_raw: target_file_id}

    # ---- L2-B / L2-C outputs ----
    chunks_by_file: dict             # {file_id: list[tuple[LineChunk, ParsingState]]}
    partitions: list                 # PartitionIR objects (all files combined)
    partition_count: int

    # ---- L2-C RAPTOR outputs ----
    raptor_nodes: list               # RAPTORNode objects

    # ---- L2-D outputs (annotated on partitions) ----
    complexity_computed: bool

    # ---- L2-E outputs ----
    persisted_count: int
    scc_groups: list                 # SCC group sets
    max_hop: int                     # Dynamic hop cap

    # ---- L3 outputs ----
    conversion_results: list         # ConversionResult objects
    validation_passed: int           # Number of conversions passing validation

    # ---- L4 outputs ----
    merge_results: list              # Per-file merge outputs from MergeAgent

    # ---- Checkpointing ----
    last_checkpoint_block: int       # Last checkpointed block number
    checkpoint_key: Optional[str]

    # ---- Error tracking ----
    errors: list[str]
    warnings: list[str]

    # ---- Tracing ----
    trace_id: str
    run_id: str
    pipeline_version: str


class PipelineStateValidator(BaseModel):
    """Pydantic model for runtime validation of PipelineState snapshots.

    Usage: ``PipelineStateValidator(**state)`` at node boundaries
    to catch schema drift early.
    """

    input_paths: list[str]
    target_runtime: str = "python"
    stage: str = PipelineStage.INIT.value
    current_file_idx: int = 0
    partition_count: int = Field(default=0, ge=0)
    persisted_count: int = Field(default=0, ge=0)
    max_hop: int = Field(default=3, ge=1, le=20)
    validation_passed: int = Field(default=0, ge=0)
    trace_id: str
    run_id: str

    @field_validator("target_runtime")
    @classmethod
    def _valid_runtime(cls, v: str) -> str:
        if v not in ("python", "pyspark"):
            raise ValueError(f"target_runtime must be 'python' or 'pyspark', got '{v}'")
        return v

    @field_validator("stage")
    @classmethod
    def _valid_stage(cls, v: str) -> str:
        valid = {s.value for s in PipelineStage}
        if v not in valid:
            raise ValueError(f"Unknown stage '{v}', must be one of {valid}")
        return v
