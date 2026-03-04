"""Show ALL block open/close events for gsh_11."""
import asyncio, hashlib
from pathlib import Path
from uuid import uuid4
from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

def make_fm(p):
    raw = p.read_bytes()
    enc = "utf-8"
    try: raw.decode("utf-8")
    except UnicodeDecodeError: enc = "latin-1"
    return FileMetadata(
        file_id=uuid4(), file_path=str(p), encoding=enc,
        content_hash=hashlib.sha256(raw).hexdigest(),
        file_size_bytes=len(raw), line_count=raw.count(b"\n")+1, lark_valid=True
    )

async def main():
    sf = Path('knowledge_base/gold_standard/gsh_11_scoring_engine.sas')
    fm = make_fm(sf)
    pairs = await run_streaming_pipeline(fm)
    events = BoundaryDetector().detect(pairs, fm.file_id)
    print(f"Total events: {len(events)}")
    for ev in events:
        ptype = ev.partition_type.value if hasattr(ev.partition_type, 'value') else ev.partition_type
        print(f"  {ptype} L{ev.line_start}-{ev.line_end}")

asyncio.run(main())
