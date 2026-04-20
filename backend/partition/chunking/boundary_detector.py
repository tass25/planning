"""BoundaryDetector + BoundaryDetectorAgent — L2-C boundary detection.

Deterministic pass: regex + StateAgent FSM transitions (~80% of blocks).
LLM pass:           Azure OpenAI GPT-4o-mini for ambiguous blocks (~20%).
                    Configurable via LLM_PROVIDER env var (azure / groq / ollama).
"""

from __future__ import annotations

import re as _re
from uuid import UUID

import structlog

from partition.base_agent import BaseAgent
from partition.models.enums import PartitionType
from partition.streaming.models import LineChunk, ParsingState
from partition.utils.retry import azure_breaker, azure_limiter

# Extracts the PROC name from the first line of a PROC block for metadata.
_PROC_NAME_RE = _re.compile(r"^\s*PROC\s+(\w+)", _re.IGNORECASE)

from .llm_boundary_resolver import LLMBoundaryResolver
from .models import COVERAGE_MAP, BlockBoundaryEvent

logger = structlog.get_logger()

# ── StateAgent block_type string → PartitionType ──────────────────────────────

_TYPE_MAP: dict[str, PartitionType] = {
    "DATA_STEP": PartitionType.DATA_STEP,
    "PROC_BLOCK": PartitionType.PROC_BLOCK,
    "SQL_BLOCK": PartitionType.SQL_BLOCK,
    "MACRO_DEFINITION": PartitionType.MACRO_DEFINITION,
    "MACRO_INVOCATION": PartitionType.MACRO_INVOCATION,
    "CONDITIONAL_BLOCK": PartitionType.CONDITIONAL_BLOCK,
    "LOOP_BLOCK": PartitionType.LOOP_BLOCK,
    "GLOBAL_STATEMENT": PartitionType.GLOBAL_STATEMENT,
    "INCLUDE_REFERENCE": PartitionType.INCLUDE_REFERENCE,
}

# A block is flagged as ambiguous when it exceeds this line count
_AMBIGUOUS_THRESHOLD = 200

# Maximum line gap allowed between consecutive GLOBAL_STATEMENTs to merge them.
_GLOBAL_MERGE_GAP = 3

import re as _re

# Regex that matches a line containing only a %PUT NOTE/WARNING/ERROR: statement
# (i.e. the %PUT is the sole content).  Used to filter out standalone
# %PUT-banner GLOBAL_STATEMENTs that should belong to the following macro call.
_PUT_ONLY_LINE = _re.compile(r"^\s*%PUT\s+(?:NOTE|WARNING|ERROR)\s*:", _re.IGNORECASE)


def _is_put_only(raw_code: str) -> bool:
    """Return True if *raw_code* contains only %PUT NOTE/WARNING/ERROR lines."""
    for line in raw_code.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not _PUT_ONLY_LINE.match(stripped):
            return False
    return True


def _merge_global_statements(
    events: list[BlockBoundaryEvent],
    file_id: UUID,
    trace_id: UUID | None,
) -> list[BlockBoundaryEvent]:
    """Merge consecutive GLOBAL_STATEMENT events within _GLOBAL_MERGE_GAP lines.

    The gold standard treats consecutive OPTIONS/LIBNAME/FILENAME/TITLE
    statements as a single multi-line GLOBAL_STATEMENT block.  This function
    collapses adjacent same-type GLOBAL events into one event spanning the
    full range.

    A GLOBAL_STATEMENT that contains ONLY ``%PUT NOTE/WARNING/ERROR:`` lines
    and was NOT merged with a "core" GLOBAL (OPTIONS/LIBNAME/FILENAME/TITLE/
    %LET) is dropped.  Such ``%PUT``-banner lines appear before macro-call
    sections and belong to the following MACRO_INVOCATION block, not to a
    standalone GLOBAL.
    """
    result: list[BlockBoundaryEvent] = []
    pending: BlockBoundaryEvent | None = None
    pending_has_core: bool = False  # True if pending contains a non-PUT line

    for ev in events:
        if ev.partition_type != PartitionType.GLOBAL_STATEMENT:
            if pending is not None:
                # Only emit the pending GLOBAL if it has non-PUT content OR was
                # merged with another GLOBAL that had core content.
                if pending_has_core:
                    result.append(pending)
                # else: drop the PUT-only standalone GLOBAL (it's a false positive)
                pending = None
                pending_has_core = False
            result.append(ev)
        else:
            ev_has_core = not _is_put_only(ev.raw_code)
            if pending is None:
                pending = ev
                pending_has_core = ev_has_core
            elif ev.line_start - pending.line_end <= _GLOBAL_MERGE_GAP:
                # Merge: extend the pending block's end to this event's end.
                pending = BlockBoundaryEvent(
                    file_id=pending.file_id,
                    partition_type=PartitionType.GLOBAL_STATEMENT,
                    line_start=pending.line_start,
                    line_end=ev.line_end,
                    raw_code=pending.raw_code + "\n" + ev.raw_code,
                    boundary_method=pending.boundary_method,
                    confidence=min(pending.confidence, ev.confidence),
                    is_ambiguous=pending.is_ambiguous or ev.is_ambiguous,
                    nesting_depth=pending.nesting_depth,
                    macro_scope={},
                    variable_scope=dict(pending.variable_scope),
                    dependency_refs=list(pending.dependency_refs),
                    test_coverage_type=pending.test_coverage_type,
                    trace_id=trace_id,
                )
                pending_has_core = pending_has_core or ev_has_core
            else:
                if pending_has_core:
                    result.append(pending)
                pending = ev
                pending_has_core = ev_has_core

    if pending is not None and pending_has_core:
        result.append(pending)

    return result


# Patterns for %MEND and %PUT NOTE:%PUT WARNING: after a block close
_MEND_RE = _re.compile(r"^\s*%MEND\b", _re.IGNORECASE)
_PUT_LOG_RE = _re.compile(r"^\s*%PUT\s+(NOTE|WARNING|ERROR)\s*:", _re.IGNORECASE)
_LET_RE = _re.compile(r"^\s*%LET\b", _re.IGNORECASE)
# Block types whose end can be extended when trailing %MEND is nearby
_EXTEND_TYPES = {
    PartitionType.DATA_STEP,
    PartitionType.PROC_BLOCK,
    PartitionType.SQL_BLOCK,
    PartitionType.CONDITIONAL_BLOCK,
    PartitionType.LOOP_BLOCK,
}
# Maximum lines to scan after block end looking for a trailing %MEND
_MEND_LOOKAHEAD = 12

# %ELSE pattern — if a line right after a CONDITIONAL_BLOCK close starts with %ELSE
_ELSE_RE = _re.compile(r"^\s*%ELSE\b", _re.IGNORECASE)

# Maximum line gap between consecutive CONDITIONAL_BLOCK events to merge as chain
_COND_CHAIN_GAP = 3


def _merge_cond_chains(
    events: list[BlockBoundaryEvent],
    chunks_with_states: list,
    file_id: UUID,
    trace_id: UUID | None,
) -> list[BlockBoundaryEvent]:
    """Merge consecutive CONDITIONAL_BLOCK events that form if/%else if/%else chains.

    When the FSM sees %if...%do...%end it emits one CONDITIONAL_BLOCK event.
    If the next non-blank/comment line is %else or %else %if, the gold
    standard treats the entire chain as a single CONDITIONAL_BLOCK.

    This merges adjacent CONDITIONAL_BLOCK events whose gap (between the end
    of one and the start of the next) is small AND where the lines between
    them start with %ELSE.

    Also extends the merged block end to include trailing TITLE/FOOTNOTE and
    GLOBAL statements immediately following the last %END; of the chain (up to
    _COND_CHAIN_GAP lines), because gold sometimes includes those in the block.
    """
    # Build a line-content map from chunks
    line_map: dict[int, str] = {}
    for chunk, _state in chunks_with_states:
        chunk_start = max(1, chunk.line_number - chunk.content.count("\n"))
        for i, ln in enumerate(chunk.content.split("\n")):
            line_map[chunk_start + i] = ln.strip()

    def _lines_between_are_else(end: int, start: int) -> bool:
        """Return True if lines end+1..start contain %ELSE (possibly with blanks)."""
        if start - end > _COND_CHAIN_GAP + 1:
            return False
        for ln_num in range(end + 1, start + 1):
            text = line_map.get(ln_num, "")
            if not text:
                continue  # blank line OK
            if _ELSE_RE.match(text):
                return True
            # If any non-blank, non-ELSE line is found, chain ends
            return False
        return False

    result: list[BlockBoundaryEvent] = []
    pending: BlockBoundaryEvent | None = None

    for ev in events:
        if ev.partition_type != PartitionType.CONDITIONAL_BLOCK:
            if pending is not None:
                result.append(pending)
                pending = None
            result.append(ev)
        else:
            if pending is None:
                pending = ev
            elif _lines_between_are_else(pending.line_end, ev.line_start):
                # Merge: extend pending to this event's end
                pending = BlockBoundaryEvent(
                    file_id=pending.file_id,
                    partition_type=PartitionType.CONDITIONAL_BLOCK,
                    line_start=pending.line_start,
                    line_end=ev.line_end,
                    raw_code=pending.raw_code + "\n" + ev.raw_code,
                    boundary_method=pending.boundary_method,
                    confidence=min(pending.confidence, ev.confidence),
                    is_ambiguous=pending.is_ambiguous or ev.is_ambiguous,
                    nesting_depth=pending.nesting_depth,
                    macro_scope={},
                    variable_scope=dict(pending.variable_scope),
                    dependency_refs=list(pending.dependency_refs),
                    test_coverage_type=pending.test_coverage_type,
                    trace_id=trace_id,
                )
            else:
                result.append(pending)
                pending = ev

    if pending is not None:
        result.append(pending)

    return result


def _extend_to_mend(
    events: list[BlockBoundaryEvent],
    chunks_with_states: list,
) -> list[BlockBoundaryEvent]:
    """Extend DATA/PROC/SQL block ends to absorb trailing %MEND (in-macro bodies).

    When a DATA_STEP/PROC_BLOCK/SQL_BLOCK is the last statement inside a macro,
    the gold standard often extends the block end to include the trailing
    blank line(s), %PUT NOTE: banner, and %MEND line.  This function applies
    that same extension heuristically.

    Pattern detected: block_end = RUN;/QUIT; line, then within 6 lines:
        [blank lines] [%PUT NOTE/WARNING/ERROR: ...] [blank lines] %MEND ...

    Args:
        events: Sorted list of detected BlockBoundaryEvents.
        chunks_with_states: The streaming pipeline output (to build line map).

    Returns:
        Updated events list with extended block ends where applicable.
    """
    if not chunks_with_states:
        return events

    # Build a line_number → stripped_content map from chunks
    line_content: dict[int, str] = {}
    for chunk, _ in chunks_with_states:
        ln = chunk.line_number
        content = chunk.content
        # For multi-line chunks, assign last line primarily; also map individual lines
        lines_in_chunk = content.split("\n")
        start_ln = ln - len(lines_in_chunk) + 1
        for i, l in enumerate(lines_in_chunk):
            line_content[start_ln + i] = l.strip()

    result = []
    for ev in events:
        if ev.partition_type not in _EXTEND_TYPES:
            result.append(ev)
            continue

        # Look ahead from ev.line_end + 1 up to ev.line_end + _MEND_LOOKAHEAD
        mend_line = None
        last_put_line = None
        for li in range(ev.line_end + 1, ev.line_end + _MEND_LOOKAHEAD + 1):
            lc = line_content.get(li, "")
            if not lc:  # blank line
                continue
            if _MEND_RE.match(lc):
                mend_line = li
                break
            elif _PUT_LOG_RE.match(lc):
                # %PUT NOTE/WARNING/ERROR: — skip-worthy, track last seen
                last_put_line = li
                continue
            elif _LET_RE.match(lc):
                # %LET inside macro body — skip past it
                continue
            else:
                # Any other non-blank content → stop extending
                break

        # Determine new end: prefer %MEND, then last %PUT if no %MEND found
        extend_to = mend_line if mend_line is not None else last_put_line

        if extend_to is not None:
            # Extend block end to include the %MEND (or last %PUT) line
            ev = BlockBoundaryEvent(
                file_id=ev.file_id,
                partition_type=ev.partition_type,
                line_start=ev.line_start,
                line_end=extend_to,
                raw_code=ev.raw_code,
                boundary_method=ev.boundary_method,
                confidence=ev.confidence,
                is_ambiguous=ev.is_ambiguous,
                nesting_depth=ev.nesting_depth,
                macro_scope=ev.macro_scope,
                variable_scope=ev.variable_scope,
                dependency_refs=ev.dependency_refs,
                test_coverage_type=ev.test_coverage_type,
                trace_id=ev.trace_id,
            )
        result.append(ev)

    return result


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

        Uses ``ParsingState.last_closed_block`` (set by StateAgent on every
        ``_close_block`` call) as the primary closure signal.  This captures:
        * Normal closes  (RUN;, QUIT;, %MEND, leading „;")
        * Single-line blocks (OPTIONS/LIBNAME/etc. that open+close in one chunk)
        * Implicit closes (new top-level keyword closes still-open DATA/PROC block)

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

        def _emit(
            pt_str: str, start: int, end: int, lines: list[str], ref: ParsingState | None
        ) -> None:
            pt = _TYPE_MAP.get(pt_str)
            if pt is None or not lines:
                return
            scope = dict(ref.variable_scope) if ref else {}
            deps = list(ref.active_dependencies) if ref else []
            depth = ref.nesting_depth if ref else 0
            # Extract specific PROC name (e.g. "SORT", "MEANS") for metadata
            extra: dict = {}
            if pt == PartitionType.PROC_BLOCK and lines:
                m = _PROC_NAME_RE.match(lines[0])
                if m:
                    extra["proc_type"] = m.group(1).upper()
            events.append(
                BlockBoundaryEvent(
                    file_id=file_id,
                    partition_type=pt,
                    line_start=start,
                    line_end=end,
                    raw_code="\n".join(lines),
                    boundary_method="lark",
                    confidence=1.0,
                    is_ambiguous=len(lines) > _AMBIGUOUS_THRESHOLD,
                    nesting_depth=depth,
                    macro_scope={},
                    variable_scope=scope,
                    dependency_refs=deps,
                    test_coverage_type=COVERAGE_MAP.get(pt, "full"),
                    trace_id=trace_id,
                    extra_metadata=extra,
                )
            )

        for chunk, state in chunks_with_states:
            lcb = state.last_closed_block  # (type, start, end) | None
            after_bt = state.current_block_type  # block type AFTER this chunk

            # ── Primary close signal ─────────────────────────────────────
            if lcb is not None:
                lcb_type, lcb_start, lcb_end = lcb

                if current_type is not None and current_type == lcb_type:
                    # Ongoing block just closed.
                    # Normal close (RUN;/QUIT;/etc.) → state is IDLE: include chunk.
                    # Implicit close (new keyword)    → state not IDLE: don't include.
                    if after_bt in (None, "IDLE"):
                        current_lines.append(chunk.content)
                    _emit(current_type, block_start, lcb_end, current_lines, state)  # type: ignore[arg-type]
                    current_lines = []
                    current_type = None
                    block_start = None

                elif current_type is None:
                    # Single-line block (open+close in this chunk): emit directly.
                    _emit(lcb_type, lcb_start, lcb_end, [chunk.content], state)

                # else: type mismatch — skip defensively (shouldn't happen)

            # ── Fallback: old IDLE-transition detection ───────────────────
            # Used when last_closed_block is not set (e.g. manually built states
            # in unit tests, or pipeline versions that don't populate the field).
            elif current_type is not None and after_bt in (None, "IDLE"):
                # FSM just went IDLE without a last_closed_block signal.
                # Include this chunk (may be RUN; or the line after the block).
                current_lines.append(chunk.content)
                line_end = chunk.line_number
                _emit(current_type, block_start, line_end, current_lines, state)  # type: ignore[arg-type]
                current_lines = []
                current_type = None
                block_start = None

            # ── Track ongoing open block ─────────────────────────────────
            if after_bt and after_bt != "IDLE":
                if current_type is None:
                    # New block just became active
                    current_type = after_bt
                    block_start = state.block_start_line or chunk.line_number
                    current_lines = []
                # Add chunk to open block.
                # Skip when lcb was just handled AND it was an implicit close
                # (the chunk's content belongs to the NEW block already stored above).
                if lcb is None or after_bt not in (None, "IDLE"):
                    current_lines.append(chunk.content)

            prev_state = state

        # ── Handle unclosed block at EOF (missing RUN; / truncated file) ─
        if current_type is not None and current_lines:
            pt = _TYPE_MAP.get(current_type)
            if pt is not None:
                raw_code = "\n".join(current_lines)
                last_line = chunks_with_states[-1][0].line_number if chunks_with_states else 0
                scope = dict(prev_state.variable_scope) if prev_state else {}
                deps = list(prev_state.active_dependencies) if prev_state else []
                depth = prev_state.nesting_depth if prev_state else 0
                events.append(
                    BlockBoundaryEvent(
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
                )

        events.sort(key=lambda e: e.line_start)
        events = _merge_global_statements(events, file_id, trace_id)
        events = _merge_cond_chains(events, chunks_with_states, file_id, trace_id)
        events = _extend_to_mend(events, chunks_with_states)
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
                if not azure_breaker.allow_request():
                    self.logger.warning(
                        "circuit_breaker_open",
                        fallback="lark_fallback",
                    )
                    event.boundary_method = "lark_fallback"
                    if event.confidence < 0.5:
                        event.partition_type = PartitionType.UNCLASSIFIED
                    resolved.append(event)
                    continue
                try:
                    async with azure_limiter:
                        llm_event = await self._llm_resolver.resolve(event)
                    azure_breaker.record_success()
                    resolved.append(llm_event)
                except Exception as exc:
                    azure_breaker.record_failure()
                    self.logger.warning(
                        "llm_resolver_failed",
                        error=str(exc),
                        fallback="lark_fallback",
                    )
                    event.boundary_method = "lark_fallback"
                    if event.confidence < 0.5:
                        event.partition_type = PartitionType.UNCLASSIFIED
                    resolved.append(event)
            else:
                resolved.append(event)

        # Step 3: final sort
        resolved.sort(key=lambda e: e.line_start)

        lark_count = sum(1 for e in resolved if e.boundary_method == "lark")
        llm_count = sum(1 for e in resolved if e.boundary_method == "llm_8b")
        fallback_count = sum(1 for e in resolved if e.boundary_method == "lark_fallback")

        self.logger.info(
            "boundary_detection_complete",
            total=len(resolved),
            lark=lark_count,
            llm=llm_count,
            fallback=fallback_count,
        )
        return resolved
