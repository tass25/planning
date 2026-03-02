"""Debug the GLOBAL_STATEMENT -> MACRO_INVOCATION / PROC_BLOCK regression."""
import asyncio, hashlib, json, logging, sys
from pathlib import Path
from uuid import uuid4
import structlog
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))
sys.path.insert(0, 'C:/Users/labou/Desktop/Stage/sas_converter')
from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

GOLD_DIR = Path('C:/Users/labou/Desktop/Stage/sas_converter/knowledge_base/gold_standard')

def load_gold(file_id):
    for gf in GOLD_DIR.glob("*.gold.json"):
        data = json.loads(gf.read_text())
        if data.get("file_id") == file_id or gf.stem.replace(".gold","") == file_id:
            return data["blocks"]
    return []

async def check_file(sas_path, gold_path, show_range=None):
    raw = sas_path.read_bytes()
    fm = FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding='utf-8',
        content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
        line_count=raw.count(b'\n')+1, lark_valid=True)
    pairs = await run_streaming_pipeline(fm)
    events = BoundaryDetector().detect(pairs, fm.file_id)
    gold_blocks = json.loads(gold_path.read_text())["blocks"]
    
    # Find GLOBAL_STATEMENT mismatches
    tol = 2
    mismatches = []
    for g in gold_blocks:
        if g["partition_type"] in ("MACRO_INVOCATION", "PROC_BLOCK"):
            # Find the detected block that overlaps most
            best = None
            for e in events:
                overlap_start = max(e.line_start, g["line_start"])
                overlap_end = min(e.line_end, g["line_end"])
                if overlap_start <= overlap_end:
                    if best is None or (overlap_end - overlap_start) > (best[1] - best[0]):
                        best = (overlap_start, overlap_end, e)
            if best and best[2].partition_type.value == "GLOBAL_STATEMENT":
                mismatches.append((g, best[2]))
    
    if mismatches:
        print(f"\n=== {sas_path.stem} ===")
        for g, e in mismatches:
            print(f"  Gold: {g['partition_type']:<25} L{g['line_start']}-{g['line_end']}")
            print(f"  Det:  {e.partition_type.value:<25} L{e.line_start}-{e.line_end}")
            print()
    
    return len(mismatches)

async def main():
    total = 0
    for sas_path in sorted(GOLD_DIR.glob("*.sas")):
        gold_path = GOLD_DIR / (sas_path.stem + ".gold.json")
        if gold_path.exists():
            n = await check_file(sas_path, gold_path)
            total += n
    print(f"\nTotal GLOBAL->MI or GLOBAL->PROC mismatches: {total}")

asyncio.run(main())
