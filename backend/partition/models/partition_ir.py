"""PartitionIR — Intermediate Representation for a single partitioned block."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Any, Optional, TypedDict

from pydantic import BaseModel, Field

from .enums import PartitionType, RiskLevel, ConversionStatus


class RAPTORNode(BaseModel):
    """A node in the RAPTOR tree built for a single SAS file.

    Levels:
        0 — leaf (one PartitionIR block)
        1 — first clustering pass
        2+ — higher-level summaries
        max_depth — root (whole-file summary)
    """

    node_id: UUID = Field(default_factory=uuid4)
    level: int
    summary: str
    summary_tier: str  # "skipped" | "groq" | "ollama_fallback" | "heuristic_fallback" | "cached"
    embedding: list[float]
    child_ids: list[str] = Field(default_factory=list)
    cluster_label: Optional[int] = None
    file_id: UUID
    partition_ids: list[str] = Field(default_factory=list)


class PartitionMetadata(TypedDict, total=False):
    """Typed schema for the keys written into PartitionIR.metadata.

    ``total=False`` means all keys are optional — agents only populate
    the fields that are relevant to their stage.
    """

    # Z3 formal verification
    z3_result: str            # "verified" | "counterexample" | "unknown" | "skipped"
    z3_patterns_checked: list[str]
    z3_repair_hint: str       # CEGAR repair prompt injected by TranslationPipeline

    # RAPTOR clustering
    raptor_cluster_id: str
    raptor_level: int

    # Complexity / strategy
    complexity_score: float
    strategy: str

    # Translation quality
    failure_mode: str
    reflexion_attempts: int

    # Test configuration
    test_coverage_type: str   # "full" | "partial" | "none"

    # Catch-all for any extra keys agents may write
    extra: dict[str, Any]


class PartitionIR(BaseModel):
    """Intermediate representation of one SAS code block.

    This is the core unit that flows through the conversion pipeline:
    partition → translate → validate → emit.

    Attributes:
        block_id: Unique identifier for this block.
        file_id: Reference to the parent FileMetadata.
        partition_type: One of the nine recognised SAS block types.
        source_code: Raw SAS source for this block.
        line_start: 1-based starting line in the original file.
        line_end: 1-based ending line in the original file.
        risk_level: Assessed conversion difficulty.
        conversion_status: Current pipeline status.
        dependencies: List of block_ids this block depends on.
        metadata: Arbitrary key/value metadata for downstream agents.
        created_at: Timestamp.
    """
    block_id: UUID = Field(default_factory=uuid4)
    file_id: UUID
    partition_type: PartitionType
    source_code: str
    line_start: int
    line_end: int
    risk_level: RiskLevel = RiskLevel.UNCERTAIN
    conversion_status: ConversionStatus = ConversionStatus.HUMAN_REVIEW
    dependencies: list[UUID] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # RAPTOR back-links (populated by RAPTORTreeBuilder)
    raptor_leaf_id: str | None = None
    raptor_cluster_id: str | None = None
    raptor_root_id: str | None = None

    @property
    def has_macros(self) -> bool:
        """True when the block is macro-related (definition or invocation)."""
        return self.partition_type in (
            PartitionType.MACRO_DEFINITION,
            PartitionType.MACRO_INVOCATION,
        )
