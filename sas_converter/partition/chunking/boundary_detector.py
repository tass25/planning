"""BoundaryDetector + BoundaryDetectorAgent — L2-C boundary detection.

Deterministic pass: regex + StateAgent FSM transitions (~80% of blocks).
LLM pass:           Ollama llama3.1:8b for ambiguous blocks (~20%).
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog

from partition.base_agent import BaseAgent, with_retry
from partition.models.enums import PartitionType
from partition.streaming.models import LineChunk, ParsingState

from .models import COVERAGE_MAP, BlockBoundaryEvent
from .llm_boundary_resolver import LLMBoundaryResolver


logger = structlog.get_logger()

# ── StateAgent block_type string → PartitionType ──────────────────────────────

_TYPE_MAP: dict[str, PartitionType] = {
    "DATA_STEP":         PartitionType.DATA_STEP,
    "PROC_BLOCK":        PartitionType.PROC_BLOCK,
    "SQL_BLOCK":         PartitionType.SQL_BLOCK,
    "MACRO_DEFINITION":  PartitionType.MACRO_DEFINITION,
    "MACRO_INVOCATION":  PartitionType.MACRO_INVOCATION,
    "CONDITIONAL_BLOCK": PartitionType.CONDITIONAL_BLOCK,
    "LOOP_BLOCK":        PartitionType.LOOP_BLOCK,
    "GLOBAL_STATEMENT":  PartitionType.GLOBAL_STATEMENT,
    "INCLUDE_REFERENCE": PartitionType.INCLUDE_REFERENCE,
}

# A block is flagged as ambiguous when it exceeds this line count
_AMBIGUOUS_THRESHOLD = 200


class BoundaryDetector:
    """Pure deterministic boundary detector using StateAgent FSM output.

    No LLM — regex + state transitions only.  Handles ~80% of real SAS files.
    """

    def detect(
        self,
        chunks_with_states: list[tuple[LineChunk, ParsingState]],
        file_id: UUID,
        trace_id: UUID | None = None,
    ) -> list[BlockBoundaryEvent]:
        """Emit a BlockBoundaryEvent for every closed SAS block.

        Args:
            chunks_with_states: Ordered pairs from the streaming pipeline.
            file_id: Source file UUID.
            trace_id: Pipeline trace UUID.

        Returns:
            List of BlockBoundaryEvents sorted by line_start.
        """
        events: list[BlockBoundaryEvent] = []
        current_lines: list[str] = []
        current_type: str | None = None
        block_start: int | None = None
        prev_state: ParsingState | None = None

        for chunk, state in chunks_with_states:
            block_type = state.current_block_type

            if block_type and block_type != "IDLE":
                if current_type is None:
                    # A new block has just opened
                    current_type = block_type
                    block_start = chunk.line_number
                current_lines.append(chunk.content)

            elif current_type is not None:
                # The FSM just transitioned back to IDLE — block closed
                pt = _TYPE_MAP.get(current_type)
                if pt is not None:
                    raw_code = "\n".join(current_lines)
                    line_end = chunk.line_number - 1 if chunk.line_number > 1 else chunk.line_number

                    scope = dict(prev_state.variable_scope) if prev_state else {}
                    macro_scope = dict(prev_state.macro_scope) if (
                        prev_state and hasattr(prev_state, "macro_scope")
                    ) else {}
                    deps = list(prev_state.active_dependencies) if prev_state else []
                    depth = prev_state.nesting_depth if prev_state else 0

                    event = BlockBoundaryEvent(
                        file_id=file_id,
                        partition_type=pt,
                        line_start=block_start,  # type: ignore[arg-type]
                        line_end=line_end,
                        raw_code=raw_code,
                        boundary_method="lark",
                        confidence=1.0,
                        is_ambiguous=len(current_lines) > _AMBIGUOUS_THRESHOLD,
                        nesting_depth=depth,
                        macro_scope=macro_scope,
                        variable_scope=scope,
                        dependency_refs=deps,
                        test_coverage_type=COVERAGE_MAP.get(pt, "full"),
                        trace_id=trace_id,
                    )
                    events.append(event)

                current_lines = []
                current_type = None
                block_start = None

            prev_state = state

        # Handle unclosed block at EOF (e.g., missing RUN;)
        if current_type is not None and current_lines:
            pt = _TYPE_MAP.get(current_type)
            if pt is not None:
                raw_code = "\n".join(current_lines)
                last_line = chunks_with_states[-1][0].line_number if chunks_with_states else 0
                scope = dict(prev_state.variable_scope) if prev_state else {}
                deps = list(prev_state.active_dependencies) if prev_state else []
                depth = prev_state.nesting_depth if prev_state else 0

                event = BlockBoundaryEvent(
                    file_id=file_id,
                    partition_type=pt,
                    line_start=block_start,  # type: ignore[arg-type]
                    line_end=last_line,
                    raw_code=raw_code,
                    boundary_method="lark_fallback",
                    confidence=0.5,
                    is_ambiguous=True,
                    nesting_depth=depth,
                    macro_scope={},
                    variable_scope=scope,
                    dependency_refs=deps,
                    test_coverage_type=COVERAGE_MAP.get(pt, "full"),
                    trace_id=trace_id,
                )
                events.append(event)

        events.sort(key=lambda e: e.line_start)
        return events


# ── Agent ─────────────────────────────────────────────────────────────────────

class BoundaryDetectorAgent(BaseAgent):
    """Orchestrates deterministic + LLM boundary detection.

    Workflow:
        1. BoundaryDetector (rule-based) — handles all blocks.
        2. LLMBoundaryResolver — re-resolves events flagged ``is_ambiguous``.
        3. Returns all events sorted by ``line_start``.
    """

    agent_name = "BoundaryDetectorAgent"

    def __init__(self, trace_id: UUID | None = None) -> None:
        super().__init__(trace_id)
        self._detector = BoundaryDetector()
        self._llm_resolver = LLMBoundaryResolver(trace_id=self.trace_id)

    async def process(  # type: ignore[override]
        self,
        chunks_with_states: list[tuple[LineChunk, ParsingState]],
        file_id: UUID,
    ) -> list[BlockBoundaryEvent]:
        """Detect all block boundaries in *chunks_with_states*.

        Args:
            chunks_with_states: Output of the streaming pipeline.
            file_id: Source file UUID.

        Returns:
            List of BlockBoundaryEvents sorted by line_start.
        """
        # Step 1: deterministic pass
        events = self._detector.detect(chunks_with_states, file_id, self.trace_id)

        # Step 2: LLM pass for ambiguous blocks
        resolved: list[BlockBoundaryEvent] = []
        for event in events:
            if event.is_ambiguous:
                self.logger.info(
                    "routing_to_llm",
                    line_start=event.line_start,
                    line_end=event.line_end,
                    lines=event.line_end - event.line_start + 1,
                )
                try:
                    llm_event = await self._llm_resolver.resolve(event)
                    resolved.append(llm_event)
                except Exception as exc:
                    self.logger.warning(
                        "llm_resolver_failed",
                        error=str(exc),
                        fallback="lark_fallback",
                    )
                    event.boundary_method = "lark_fallback"
                    resolved.append(event)
            else:
                resolved.append(event)

        # Step 3: final sort
        resolved.sort(key=lambda e: e.line_start)

        lark_count    = sum(1 for e in resolved if e.boundary_method == "lark")
        llm_count     = sum(1 for e in resolved if e.boundary_method == "llm_8b")
        fallback_count = sum(1 for e in resolved if e.boundary_method == "lark_fallback")

        self.logger.info(
            "boundary_detection_complete",
            total=len(resolved),
            lark=lark_count,
            llm=llm_count,
            fallback=fallback_count,
        )
        return resolved
