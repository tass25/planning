import json, asyncio, hashlib
from pathlib import Path
from uuid import uuid4
from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

GOLD_DIR = Path("knowledge_base/gold_standard")

async def run():
    stem = "gsh_04_clinical_trial"
    gold = json.load(open(GOLD_DIR / f"{stem}.gold.json"))
    sas_path = GOLD_DIR / f"{stem}.sas"
    raw = sas_path.read_bytes()
    fm = FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding="utf-8",
        content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
        line_count=raw.count(b"\n")+1, lark_valid=True)
    pairs = await run_streaming_pipeline(fm)
    events = BoundaryDetector().detect(pairs, fm.file_id)
    
    print("=== GOLD BLOCKS ===")
    for b in gold["blocks"]:
        ls = b["line_start"]; le = b["line_end"]
        print(f"  {b['partition_type']:25s} L{ls}-{le}")
    
    print("\n=== DETECTED BLOCKS ===")
    for e in events:
        print(f"  {e.partition_type.value:25s} L{e.line_start}-{e.line_end}")
    
    print("\n=== MISSES ===")
    for b in gold["blocks"]:
        gs, ge = b["line_start"], b["line_end"]
        pt = b["partition_type"]
        det_same = [e for e in events if e.partition_type.value == pt]
        matched = any(abs(d.line_start-gs)<=2 and abs(d.line_end-ge)<=2 for d in det_same)
        if not matched:
            best = min(det_same, key=lambda d: abs(d.line_start-gs)+abs(d.line_end-ge), default=None)
            if best:
                print(f"  MISS: {pt} gold L{gs}-{ge} -> det L{best.line_start}-{best.line_end}")
            else:
                print(f"  MISS: {pt} gold L{gs}-{ge} -> NONE")

asyncio.run(run())
