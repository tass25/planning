"""Detailed analysis of MACRO_DEFINITION misses."""
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

GOLD_DIR = Path("C:/Users/labou/Desktop\Stage\sas_converter\knowledge_base\gold_standard")
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
    
    macro_def_missed = []

    for sas_file in sas_files:
        gold_file = sas_file.with_suffix("").with_suffix(".gold.json")
        with open(gold_file) as f:
            gold_data = json.load(f)
        gold_blocks = gold_data["blocks"]

        fm = make_meta(sas_file)
        pairs = await run_streaming_pipeline(fm)
        events = BoundaryDetector().detect(pairs, fm.file_id)
        detected = [(e.partition_type.value, e.line_start, e.line_end) for e in events]
        text_lines = sas_file.read_text(encoding="utf-8", errors="replace").splitlines()

        for g in gold_blocks:
            g_type, g_start, g_end = g["partition_type"], g["line_start"], g["line_end"]
            if g_type != "MACRO_DEFINITION":
                continue
            matched = any(matches(g_type, g_start, g_end, dt, ds, de) for dt, ds, de in detected)
            if matched:
                continue
            
            # Find detected MACRO_DEFINITION overlapping this gold block
            same_type = [(dt, ds, de) for dt, ds, de in detected if dt == "MACRO_DEFINITION" and (ds <= g_start <= de or g_start <= ds <= g_end)]
            other_type = [(dt, ds, de) for dt, ds, de in detected if dt != "MACRO_DEFINITION" and (ds <= g_start <= de or g_start <= ds <= g_end)]
            
            # For whole-body: check if last line has %mend
            gold_last_line = text_lines[g_end-1].strip() if g_end <= len(text_lines) else ""
            is_whole_body = "%mend" in gold_last_line.lower()
            
            for dt, ds, de in same_type:
                macro_def_missed.append({
                    "file": sas_file.name,
                    "gold": (g_start, g_end),
                    "det": (ds, de),
                    "end_delta": de - g_end,
                    "start_delta": ds - g_start,
                    "is_whole_body": is_whole_body,
                    "gold_last_line": gold_last_line,
                })
    
    # Categorize
    whole_body = [m for m in macro_def_missed if m["is_whole_body"]]
    header_only = [m for m in macro_def_missed if not m["is_whole_body"]]
    
    print(f"MACRO_DEFINITION misses (same type):")
    print(f"  Whole-body (ends with %mend): {len(whole_body)}")
    for m in whole_body[:5]:
        print(f"    {m['file']}: gold={m['gold']}, det={m['det']}, end_delta={m['end_delta']}")
    
    print(f"  Header-only (no %mend at gold end): {len(header_only)}")
    for m in header_only[:10]:
        print(f"    {m['file']}: gold={m['gold']}, det={m['det']}, end_delta={m['end_delta']}, start_delta={m['start_delta']}")
        print(f"      gold end line: {m['gold_last_line'][:60]}")

asyncio.run(main())
