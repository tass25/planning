"""Detailed analysis of GLOBAL_STATEMENT misses."""
import asyncio, hashlib, json, logging, sys
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
    
    global_missed = []
    macro_inv_missed = []

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
            matched = any(matches(g_type, g_start, g_end, dt, ds, de) for dt, ds, de in detected)
            if matched:
                continue

            # Find closest same-type detected
            same_type = [(dt, ds, de) for dt, ds, de in detected if dt == g_type and
                         (abs(ds - g_start) <= 10 or abs(de - g_end) <= 10 or ds <= g_start <= de)]
            other = [(dt, ds, de) for dt, ds, de in detected if dt != g_type and
                     (ds <= g_start <= de or g_start <= ds <= g_end)]

            if g_type == "GLOBAL_STATEMENT" and same_type:
                best = min(same_type, key=lambda x: abs(x[1]-g_start))
                snippet = "\n".join(f"[{i+g_start-1}] {l[:70]}" for i, l in enumerate(text_lines[g_start-2:g_end+2]))
                global_missed.append({
                    "file": sas_file.name,
                    "gold": (g_start, g_end),
                    "det": best,
                    "end_delta": best[2] - g_end,
                    "start_delta": best[1] - g_start,
                    "snippet": snippet[:300],
                })
            elif g_type == "MACRO_INVOCATION" and same_type:
                best = min(same_type, key=lambda x: abs(x[1]-g_start))
                snippet = "\n".join(f"[{i+g_start}] {l[:70]}" for i, l in enumerate(text_lines[g_start-1:g_end]))
                macro_inv_missed.append({
                    "file": sas_file.name,
                    "gold": (g_start, g_end),
                    "det": best,
                    "end_delta": best[2] - g_end,
                    "start_delta": best[1] - g_start,
                    "snippet": snippet[:300],
                    "gold_size": g_end - g_start + 1,
                })

    print(f"=== GLOBAL_STATEMENT misses (same type): {len(global_missed)} ===")
    for m in global_missed[:10]:
        print(f"\n  {m['file']}: gold={m['gold']}, det={m['det']}, end_delta={m['end_delta']}, start_delta={m['start_delta']}")
        print(f"  snippet:\n{m['snippet']}")
    
    print(f"\n=== MACRO_INVOCATION misses (same type): {len(macro_inv_missed)} ===")
    for m in macro_inv_missed[:10]:
        print(f"\n  {m['file']}: gold={m['gold']} ({m['gold_size']} lines), det={m['det']}, end_delta={m['end_delta']}, start_delta={m['start_delta']}")
        print(f"  snippet:\n{m['snippet']}")

asyncio.run(main())
