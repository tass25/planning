"""PartitionIR — Intermediate Representation for a single partitioned block."""

from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Any

from pydantic import BaseModel, Field

from .enums import PartitionType, RiskLevel, ConversionStatus


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
