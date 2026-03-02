"""
Debug gsh_11 detection in detail around L473+
"""
import asyncio, hashlib
from pathlib import Path
from uuid import uuid4
import sys
sys.path.insert(0, str(Path(__file__).parent))
from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

async def main():
    sas_path = Path('knowledge_base/gold_standard/gsh_11_scoring_engine.sas')
    raw = sas_path.read_bytes()
    enc = "utf-8"
    try: raw.decode("utf-8")
    except UnicodeDecodeError: enc = "latin-1"
    fm = FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding=enc,
        content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
        line_count=raw.count(b"\n")+1, lark_valid=True)

    pairs = await run_streaming_pipeline(fm)
    det_events = BoundaryDetector().detect(pairs, fm.file_id)

    print("=== gsh_11 detected blocks (L400-700) ===")
    for ev in det_events:
        if ev.line_start >= 400 and ev.line_start <= 700:
            print(f"  {ev.partition_type:25s} L{ev.line_start}-{ev.line_end}")

asyncio.run(main())
