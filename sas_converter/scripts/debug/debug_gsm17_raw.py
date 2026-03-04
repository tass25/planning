"""Trace gsm_17 raw events before post-processing."""
import asyncio, hashlib, logging, sys
from pathlib import Path
from uuid import uuid4

import structlog
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))

sys.path.insert(0, "C:/Users/labou/Desktop/Stage/sas_converter")

from partition.chunking.boundary_detector import (
    BoundaryDetector, _merge_cond_chains, _merge_global_statements, _extend_to_mend
)
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

GOLD_DIR = Path("C:/Users/labou/Desktop/Stage/sas_converter/knowledge_base/gold_standard")

def make_meta(sas_path):
    raw = sas_path.read_bytes()
    enc = "utf-8"
    try: raw.decode("utf-8")
    except UnicodeDecodeError: enc = "latin-1"
    return FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding=enc,
        content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
        line_count=raw.count(b"\n")+1, lark_valid=True)

async def main():
    sas_file = GOLD_DIR / "gsm_17_etl_incremental.sas"
    fm = make_meta(sas_file)
    pairs = await run_streaming_pipeline(fm)

    # Manually replicate detect() to see before/after post-processing
    from partition.chunking.boundary_detector import (
        _TYPE_MAP, _AMBIGUOUS_THRESHOLD, COVERAGE_MAP
    )
    from partition.chunking.models import BlockBoundaryEvent
    from partition.models.enums import PartitionType
    
    events_raw = []
    current_lines = []
    current_type = None
    block_start = None
    prev_state = None
    file_id = fm.file_id

    def _emit(pt_str, start, end, lines, ref):
        pt = _TYPE_MAP.get(pt_str)
        if pt is None or not lines:
            return
        scope = dict(ref.variable_scope) if ref else {}
        deps = list(ref.active_dependencies) if ref else []
        depth = ref.nesting_depth if ref else 0
        events_raw.append(BlockBoundaryEvent(
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
            trace_id=None,
        ))

    for chunk, state in pairs:
        lcb = state.last_closed_block
        after_bt = state.current_block_type

        if lcb is not None:
            lcb_type, lcb_start, lcb_end = lcb
            if current_type is not None and current_type == lcb_type:
                if after_bt in (None, "IDLE"):
                    current_lines.append(chunk.content)
                _emit(current_type, block_start, lcb_end, current_lines, state)
                current_lines = []
                current_type = None
                block_start = None
            elif current_type is None:
                _emit(lcb_type, lcb_start, lcb_end, [chunk.content], state)
        elif current_type is not None and after_bt in (None, "IDLE"):
            current_lines.append(chunk.content)
            _emit(current_type, block_start, chunk.line_number, current_lines, state)
            current_lines = []
            current_type = None
            block_start = None

        if after_bt and after_bt != "IDLE":
            if current_type is None:
                current_type = after_bt
                block_start = state.block_start_line or chunk.line_number
                current_lines = []
            if lcb is None or after_bt not in (None, "IDLE"):
                current_lines.append(chunk.content)

        prev_state = state

    events_raw.sort(key=lambda e: e.line_start)
    
    print("=== RAW events (before post-processing) L140-175 ===")
    for e in events_raw:
        if 140 <= e.line_start <= 180 or 140 <= e.line_end <= 180:
            print(f"  {e.partition_type.value:<25} L{e.line_start}-{e.line_end}")
    
    print("\n=== After _merge_global_statements ===")
    ev2 = _merge_global_statements(events_raw, file_id, None)
    for e in ev2:
        if 140 <= e.line_start <= 180 or 140 <= e.line_end <= 180:
            print(f"  {e.partition_type.value:<25} L{e.line_start}-{e.line_end}")
    
    print("\n=== After _merge_cond_chains ===")
    ev3 = _merge_cond_chains(ev2, pairs, file_id, None)
    for e in ev3:
        if 140 <= e.line_start <= 180 or 140 <= e.line_end <= 180:
            print(f"  {e.partition_type.value:<25} L{e.line_start}-{e.line_end}")
    
    print("\n=== After _extend_to_mend ===")
    ev4 = _extend_to_mend(ev3, pairs)
    for e in ev4:
        if 140 <= e.line_start <= 180 or 140 <= e.line_end <= 180:
            print(f"  {e.partition_type.value:<25} L{e.line_start}-{e.line_end}")

asyncio.run(main())
