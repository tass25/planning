"""Detailed MACRO_DEFINITION miss analysis at 79.3%."""
import asyncio, hashlib, json, logging, sys
from collections import defaultdict
from pathlib import Path
from uuid import uuid4

import structlog
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))

sys.path.insert(0, "C:/Users/labou/Desktop/Stage/sas_converter")

from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

GOLD_DIR = Path("C:/Users/labou/Desktop/Stage/sas_converter/knowledge_base/gold_standard")
TOLERANCE = 2

def make_meta(sas_path):
    raw = sas_path.read_bytes()
    enc = "utf-8"
    try: raw.decode("utf-8")
    except UnicodeDecodeError: enc = "latin-1"
    return FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding=enc,
        content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
        line_count=raw.count(b"\n")+1, lark_valid=True)

def matches(g_type, g_start, g_end, d_type, d_start, d_end):
    return (g_type == d_type
            and abs(g_start - d_start) <= TOLERANCE
            and abs(g_end - d_end) <= TOLERANCE)

async def main():
    sas_files = sorted(GOLD_DIR.glob("*.sas"))
    
    missed = []
    matched_wrong_end = []

    for sas_file in sas_files:
        gold_file = sas_file.with_suffix("").with_suffix(".gold.json")
        with open(gold_file) as f:
            gold_data = json.load(f)
        gold_blocks = gold_data["blocks"]

        fm = make_meta(sas_file)
        pairs = await run_streaming_pipeline(fm)
        events = BoundaryDetector().detect(pairs, fm.file_id)
        detected = [(e.partition_type.value, e.line_start, e.line_end) for e in events]

        for g in gold_blocks:
            g_type, g_start, g_end = g["partition_type"], g["line_start"], g["line_end"]
            if g_type != "MACRO_DEFINITION":
                continue
            
            matched = any(matches(g_type, g_start, g_end, dt, ds, de) for dt, ds, de in detected)
            if matched:
                continue
            
            # Find closest same-type detection
            same_type = [(dt, ds, de) for dt, ds, de in detected if dt == "MACRO_DEFINITION"]
            closest = None
            for dt, ds, de in same_type:
                if abs(ds - g_start) <= 5:  # rough start match
                    closest = (dt, ds, de)
                    break
            
            name = g.get("name", "")
            if closest:
                end_delta = closest[2] - g_end
                start_delta = closest[1] - g_start
                matched_wrong_end.append({
                    "file": sas_file.name,
                    "gold": (g_start, g_end),
                    "det":  (closest[1], closest[2]),
                    "end_delta": end_delta,
                    "start_delta": start_delta,
                    "name": name,
                })
            else:
                missed.append({
                    "file": sas_file.name,
                    "gold": (g_start, g_end),
                    "name": name,
                })
    
    print(f"MACRO_DEFINITION misses: {len(matched_wrong_end) + len(missed)} total")
    print(f"  - Wrong end (same-start, diff-end): {len(matched_wrong_end)}")
    print(f"  - Completely missing:               {len(missed)}")
    
    print("\n=== Wrong-end cases (top 20 by abs end_delta) ===")
    sorted_wrong = sorted(matched_wrong_end, key=lambda x: abs(x['end_delta']), reverse=True)
    for m in sorted_wrong[:20]:
        print(f"  {m['file']:<40} gold=L{m['gold'][0]}-{m['gold'][1]} det=L{m['det'][0]}-{m['det'][1]}"
              f"  end_delta={m['end_delta']:+d}  start_delta={m['start_delta']:+d}  name={m['name']}")
    
    print("\n=== Completely missing ===")
    for m in missed[:15]:
        print(f"  {m['file']:<40} gold=L{m['gold'][0]}-{m['gold'][1]}  name={m['name']}")
    
    print("\n=== End-delta distribution ===")
    deltas = [m["end_delta"] for m in matched_wrong_end]
    neg = [d for d in deltas if d < -2]
    pos = [d for d in deltas if d > 2]
    print(f"  Too short (end < gold-2): {len(neg)}, avg={(sum(neg)/len(neg) if neg else 0):.1f}")
    print(f"  Too long  (end > gold+2): {len(pos)}, avg={(sum(pos)/len(pos) if pos else 0):.1f}")

asyncio.run(main())
