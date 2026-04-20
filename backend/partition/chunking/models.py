"""BlockBoundaryEvent — data model for a detected SAS block boundary."""

from __future__ import annotations

from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from partition.models.enums import PartitionType

# ── Coverage map: which partition types get exec()-tested vs structural only ──

COVERAGE_MAP: dict[PartitionType, str] = {
    PartitionType.DATA_STEP: "full",
    PartitionType.PROC_BLOCK: "full",
    PartitionType.MACRO_DEFINITION: "full",
    PartitionType.MACRO_INVOCATION: "full",
    PartitionType.SQL_BLOCK: "full",
    PartitionType.CONDITIONAL_BLOCK: "structural_only",
    PartitionType.LOOP_BLOCK: "structural_only",
    PartitionType.GLOBAL_STATEMENT: "structural_only",
    PartitionType.INCLUDE_REFERENCE: "structural_only",
    PartitionType.UNCLASSIFIED: "structural_only",
}


class BlockBoundaryEvent(BaseModel):
    """Emitted by BoundaryDetectorAgent for every detected SAS block.

    Attributes:
        event_id: Unique identifier for this detection event.
        file_id: UUID of the source file (from FileMetadata).
        partition_type: One of the 9 canonical SAS partition types.
        line_start: 1-based starting line of the block.
        line_end: 1-based ending line of the block.
        raw_code: Full text of the block.
        boundary_method: How the boundary was detected:
            ``"lark"``         — deterministic rule-based detection,
            ``"llm_8b"``       — resolved by Ollama Llama 3.1 8B,
            ``"lark_fallback"``— LLM failed, Lark result kept.
        confidence: 1.0 for lark; LLM-provided value for llm_8b.
        is_ambiguous: True when block exceeds 200 lines with no clear end.
        nesting_depth: Depth of %DO/%IF nesting at point of detection.
        macro_scope: %MACRO context variables at block entry.
        variable_scope: DATA step / PROC variables at block entry.
        dependency_refs: %INCLUDE / LIBNAME references in this block.
        test_coverage_type: ``"full"`` or ``"structural_only"``.
        trace_id: Pipeline trace UUID for end-to-end correlation.
    """

    event_id: UUID = Field(default_factory=uuid4)
    file_id: UUID
    partition_type: PartitionType
    line_start: int
    line_end: int
    raw_code: str
    boundary_method: str = "lark"  # "lark" | "llm_8b" | "lark_fallback"
    confidence: float = 1.0
    is_ambiguous: bool = False
    nesting_depth: int = 0
    macro_scope: dict[str, str] = Field(default_factory=dict)
    variable_scope: dict[str, str] = Field(default_factory=dict)
    dependency_refs: list[str] = Field(default_factory=list)
    test_coverage_type: str = "full"
    trace_id: Optional[UUID] = None
    extra_metadata: dict = Field(default_factory=dict)  # e.g. {"proc_type": "SORT"}
