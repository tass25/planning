import json, asyncio, hashlib
from pathlib import Path
from uuid import uuid4
from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

async def run():
    stem = "gsh_10_financial_recon"
    sas_path = Path(f"knowledge_base/gold_standard/{stem}.sas")
    
    raw = sas_path.read_bytes()
    fm = FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding="latin-1",
        content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
        line_count=raw.count(b"\n")+1, lark_valid=True)
    pairs = await run_streaming_pipeline(fm)
    events = BoundaryDetector().detect(pairs, fm.file_id)
    
    print("=== All events around L700-810 ===")
    for e in events:
        if 700 <= e.line_start <= 810 or 700 <= e.line_end <= 810:
            print(f"  {e.partition_type.value:25s} L{e.line_start}-{e.line_end}")

asyncio.run(run())
