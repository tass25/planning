"""Check raw_code of GLOBAL events to understand put-only detection."""
import asyncio, hashlib, sys, logging
from pathlib import Path
from uuid import uuid4
import structlog
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))
sys.path.insert(0, 'C:/Users/labou/Desktop/Stage/sas_converter')
from partition.chunking.boundary_detector import BoundaryDetector, _merge_global_statements
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

GOLD = Path('C:/Users/labou/Desktop/Stage/sas_converter/knowledge_base/gold_standard')

async def check_raw(fname, line_range):
    sas_path = GOLD / fname
    raw = sas_path.read_bytes()
    fm = FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding='utf-8',
        content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
        line_count=raw.count(b'\n')+1, lark_valid=True)
    pairs = await run_streaming_pipeline(fm)
    det = BoundaryDetector()
    events_raw = list(det._state_agent.process_all(pairs))
    ev2 = _merge_global_statements(events_raw, fm.file_id, None)
    lo, hi = line_range
    for e in ev2:
        if lo <= e.line_start <= hi or lo <= e.line_end <= hi:
            print(f'  {e.partition_type.value:<25} L{e.line_start}-{e.line_end}')
            print(f'    raw_code[:80]: {repr(e.raw_code[:80])}')

async def main():
    print("=== gsh_12 L668-700 ===")
    await check_raw('gsh_12_data_governance.sas', (668, 700))
    print()
    print("=== gsh_01 L567-578 ===")
    await check_raw('gsh_01_enterprise_etl.sas', (567, 578))

asyncio.run(main())
