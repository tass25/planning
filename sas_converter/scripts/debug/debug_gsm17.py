"""Detailed trace for gsm_17 to understand why MACRO_INVOCATION disappears."""
import asyncio, hashlib, logging, sys
from pathlib import Path
from uuid import uuid4

import structlog
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))

sys.path.insert(0, "C:/Users/labou/Desktop/Stage/sas_converter")

from partition.chunking.boundary_detector import BoundaryDetector
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
    text_lines = sas_file.read_text(encoding="utf-8", errors="replace").splitlines()
    
    # Show lines 145-175
    print("=== gsm_17 lines 145-175 ===")
    for i, l in enumerate(text_lines[144:175], start=145):
        print(f"  {i:4d}: {l}")
    
    fm = make_meta(sas_file)
    pairs = await run_streaming_pipeline(fm)
    events = BoundaryDetector().detect(pairs, fm.file_id)
    
    print("\n=== All detected events (L140-L180 range) ===")
    for e in events:
        if 140 <= e.line_start <= 180 or 140 <= e.line_end <= 180:
            print(f"  {e.partition_type.value:<25} L{e.line_start}-{e.line_end}")
    
    print("\n=== All detected events ===")
    for e in events:
        print(f"  {e.partition_type.value:<25} L{e.line_start}-{e.line_end}")

asyncio.run(main())
