"""Pydantic models for the streaming layer — LineChunk and ParsingState."""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class LineChunk(BaseModel):
    """A single logical SAS statement (one or more physical lines coalesced).

    Attributes:
        file_id: UUID of the source file (from FileMetadata).
        line_number: 1-based line number where this chunk ends.
        content: Full text of the coalesced statement, whitespace-stripped.
        byte_offset: Cumulative byte offset in the source file.
        is_continuation: True if the chunk was flushed at EOF without a
            terminating semicolon (incomplete statement).
    """
    file_id: UUID
    line_number: int
    content: str
    byte_offset: int
    is_continuation: bool = False


class ParsingState(BaseModel):
    """Finite-state machine snapshot maintained by StateAgent.

    Attributes:
        current_block_type: Active block type string, ``"IDLE"`` when between
            blocks, or ``None`` at initialisation.
        block_start_line: Line number where the current block opened.
        nesting_depth: Depth of ``%DO`` / ``%IF`` nesting inside macros.
        macro_stack: Stack of ``%MACRO`` names currently open.
        variable_scope: Most-recently assigned variables (name → "assigned").
        active_dependencies: ``%INCLUDE`` / ``LIBNAME`` references seen in
            the current block.
        in_comment: Whether we are inside a ``/* … */`` block comment.
        in_string: Whether we are inside a multi-line string literal.
    """
    current_block_type: Optional[str] = None
    block_start_line: Optional[int] = None
    nesting_depth: int = 0
    macro_stack: list[str] = Field(default_factory=list)
    variable_scope: dict[str, str] = Field(default_factory=dict)
    active_dependencies: list[str] = Field(default_factory=list)
    in_comment: bool = False
    in_string: bool = False
    # Set when a block closes so BoundaryDetector can capture single-line blocks
    # that open and close within the same chunk (returning IDLE state).
    # Format: (block_type_str, block_start_line, block_end_line)
    last_closed_block: Optional[tuple[str, int, int]] = None
    # Tracks the start of a leading comment/blank region in IDLE state.
    # When the next block opens, this is used as the block_start_line so that
    # block boundaries include section-header comments (matching gold offsets).
    pending_block_start: Optional[int] = None
