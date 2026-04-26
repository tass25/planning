"""Tests for BoundaryDetectorAgent and PartitionBuilderAgent (L2-C).

Run with:
    cd sas_converter
    ../venv/Scripts/python -m pytest tests/test_boundary_detector.py -v
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from partition.chunking.boundary_detector import BoundaryDetector
from partition.chunking.models import BlockBoundaryEvent
from partition.chunking.partition_builder import PartitionBuilderAgent
from partition.models.enums import PartitionType
from partition.streaming.models import LineChunk, ParsingState

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_chunk(line_number: int, content: str, file_id=None) -> LineChunk:
    return LineChunk(
        file_id=file_id or uuid4(),
        line_number=line_number,
        content=content,
        byte_offset=0,
    )


def _make_state(block_type: str | None, nesting: int = 0) -> ParsingState:
    return ParsingState(
        current_block_type=block_type,
        nesting_depth=nesting,
    )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── BoundaryDetector (unit tests) ─────────────────────────────────────────────


class TestBoundaryDetector:
    def test_simple_data_step(self):
        """DATA step: open on line 1, close on line 3."""
        file_id = uuid4()
        pairs = [
            (_make_chunk(1, "DATA work.out;", file_id), _make_state("DATA_STEP")),
            (_make_chunk(2, "  x = 1;", file_id), _make_state("DATA_STEP")),
            (_make_chunk(3, "RUN;", file_id), _make_state("IDLE")),
        ]
        detector = BoundaryDetector()
        events = detector.detect(pairs, file_id)

        assert len(events) == 1
        e = events[0]
        assert e.partition_type == PartitionType.DATA_STEP
        assert e.line_start == 1
        assert e.boundary_method == "lark"
        assert e.test_coverage_type == "full"

    def test_proc_block(self):
        file_id = uuid4()
        pairs = [
            (_make_chunk(1, "PROC MEANS DATA=work.out;", file_id), _make_state("PROC_BLOCK")),
            (_make_chunk(2, "  VAR x;", file_id), _make_state("PROC_BLOCK")),
            (_make_chunk(3, "RUN;", file_id), _make_state("IDLE")),
        ]
        events = BoundaryDetector().detect(pairs, file_id)
        assert len(events) == 1
        assert events[0].partition_type == PartitionType.PROC_BLOCK

    def test_macro_definition(self):
        file_id = uuid4()
        pairs = [
            (_make_chunk(1, "%MACRO foo;", file_id), _make_state("MACRO_DEFINITION")),
            (_make_chunk(2, "  %PUT hi;", file_id), _make_state("MACRO_DEFINITION")),
            (_make_chunk(3, "%MEND foo;", file_id), _make_state("IDLE")),
        ]
        events = BoundaryDetector().detect(pairs, file_id)
        assert len(events) == 1
        assert events[0].partition_type == PartitionType.MACRO_DEFINITION
        assert events[0].test_coverage_type == "full"

    def test_global_statement_is_structural_only(self):
        file_id = uuid4()
        pairs = [
            (_make_chunk(1, "LIBNAME mylib '/data';", file_id), _make_state("GLOBAL_STATEMENT")),
            (_make_chunk(2, "DATA work.x;", file_id), _make_state("IDLE")),
        ]
        events = BoundaryDetector().detect(pairs, file_id)
        assert len(events) == 1
        assert events[0].test_coverage_type == "structural_only"

    def test_multiple_blocks(self):
        """Two consecutive DATA steps emit two events."""
        file_id = uuid4()
        pairs = [
            (_make_chunk(1, "DATA a;", file_id), _make_state("DATA_STEP")),
            (_make_chunk(2, "RUN;", file_id), _make_state("IDLE")),
            (_make_chunk(3, "DATA b;", file_id), _make_state("DATA_STEP")),
            (_make_chunk(4, "RUN;", file_id), _make_state("IDLE")),
        ]
        events = BoundaryDetector().detect(pairs, file_id)
        assert len(events) == 2
        assert events[0].line_start == 1
        assert events[1].line_start == 3

    def test_ambiguous_flag_large_block(self):
        """A block > 200 lines is flagged as ambiguous."""
        file_id = uuid4()
        pairs = (
            [(_make_chunk(1, "DATA big;", file_id), _make_state("DATA_STEP"))]
            + [
                (_make_chunk(i, f"  x{i}=1;", file_id), _make_state("DATA_STEP"))
                for i in range(2, 202)
            ]
            + [(_make_chunk(202, "RUN;", file_id), _make_state("IDLE"))]
        )
        events = BoundaryDetector().detect(pairs, file_id)
        assert len(events) == 1
        assert events[0].is_ambiguous is True

    def test_no_blocks_returns_empty(self):
        file_id = uuid4()
        pairs = [
            (_make_chunk(1, "* comment;", file_id), _make_state("IDLE")),
        ]
        events = BoundaryDetector().detect(pairs, file_id)
        assert events == []

    def test_unclosed_block_at_eof(self):
        """A block open at EOF should still be emitted (lark_fallback)."""
        file_id = uuid4()
        pairs = [
            (_make_chunk(1, "DATA unclosed;", file_id), _make_state("DATA_STEP")),
            (_make_chunk(2, "  x = 1;", file_id), _make_state("DATA_STEP")),
            # No RUN; — block never closes
        ]
        events = BoundaryDetector().detect(pairs, file_id)
        assert len(events) == 1
        assert events[0].boundary_method == "lark_fallback"
        assert events[0].is_ambiguous is True

    def test_events_sorted_by_line_start(self):
        """Events must be sorted ascending by line_start even if internally out of order."""
        file_id = uuid4()
        pairs = [
            (_make_chunk(5, "LIBNAME x '/foo';", file_id), _make_state("GLOBAL_STATEMENT")),
            (_make_chunk(6, "DATA a;", file_id), _make_state("IDLE")),
            (_make_chunk(7, "DATA a;", file_id), _make_state("DATA_STEP")),
            (_make_chunk(8, "RUN;", file_id), _make_state("IDLE")),
        ]
        events = BoundaryDetector().detect(pairs, file_id)
        line_starts = [e.line_start for e in events]
        assert line_starts == sorted(line_starts)


# ── PartitionBuilderAgent ─────────────────────────────────────────────────────


class TestPartitionBuilderAgent:
    def _make_event(self, pt: PartitionType, line_start=1, line_end=3) -> BlockBoundaryEvent:
        return BlockBoundaryEvent(
            file_id=uuid4(),
            partition_type=pt,
            line_start=line_start,
            line_end=line_end,
            raw_code="DATA x; x=1; RUN;",
            boundary_method="lark",
            test_coverage_type="full",
        )

    def test_builds_partition_ir(self):
        events = [self._make_event(PartitionType.DATA_STEP)]
        agent = PartitionBuilderAgent()
        partitions = _run(agent.process(events))
        assert len(partitions) == 1
        p = partitions[0]
        assert p.partition_type == PartitionType.DATA_STEP
        assert p.source_code == "DATA x; x=1; RUN;"
        assert p.line_start == 1
        assert p.line_end == 3

    def test_metadata_contains_content_hash(self):
        events = [self._make_event(PartitionType.MACRO_DEFINITION)]
        agent = PartitionBuilderAgent()
        partitions = _run(agent.process(events))
        assert "content_hash" in partitions[0].metadata
        assert len(partitions[0].metadata["content_hash"]) == 64  # SHA-256 hex

    def test_metadata_placeholder_fields(self):
        events = [self._make_event(PartitionType.SQL_BLOCK)]
        agent = PartitionBuilderAgent()
        p = _run(agent.process(events))[0]
        assert p.metadata["raptor_leaf_id"] is None
        assert p.metadata["scc_id"] is None

    def test_empty_input_returns_empty(self):
        agent = PartitionBuilderAgent()
        partitions = _run(agent.process([]))
        assert partitions == []

    def test_preserves_order(self):
        events = [
            self._make_event(PartitionType.DATA_STEP, line_start=1),
            self._make_event(PartitionType.PROC_BLOCK, line_start=5),
            self._make_event(PartitionType.MACRO_DEFINITION, line_start=10),
        ]
        agent = PartitionBuilderAgent()
        partitions = _run(agent.process(events))
        types = [p.partition_type for p in partitions]
        assert types == [
            PartitionType.DATA_STEP,
            PartitionType.PROC_BLOCK,
            PartitionType.MACRO_DEFINITION,
        ]
