"""Debug MACRO_INVOCATION <-> CONDITIONAL_BLOCK confusion + MACRO_DEFINITION -> LOOP_BLOCK."""
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

cases_cond_as_macro   = []  # gold=MACRO_INVOCATION, det=CONDITIONAL_BLOCK
cases_macro_as_cond   = []  # gold=CONDITIONAL_BLOCK, det=MACRO_INVOCATION
cases_macrodef_as_loop = []  # gold=MACRO_DEFINITION, det=LOOP_BLOCK

async def main():
    sas_files = sorted(GOLD_DIR.glob("*.sas"))

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

            # Find detected blocks overlapping this gold block
            overlapping = [
                (dt, ds, de) for dt, ds, de in detected
                if ds <= g_start <= de or g_start <= ds <= g_end
            ]

            for dt, ds, de in overlapping:
                snippet = "\n".join(text_lines[max(0, ds-1):min(len(text_lines), ds+6)])
                info = {
                    "file": sas_file.name,
                    "gold": (g_type, g_start, g_end),
                    "det":  (dt, ds, de),
                    "snippet": snippet[:300],
                }
                if g_type == "MACRO_INVOCATION" and dt == "CONDITIONAL_BLOCK":
                    cases_cond_as_macro.append(info)
                elif g_type == "CONDITIONAL_BLOCK" and dt == "MACRO_INVOCATION":
                    cases_macro_as_cond.append(info)
                elif g_type == "MACRO_DEFINITION" and dt == "LOOP_BLOCK":
                    cases_macrodef_as_loop.append(info)

    print(f"\n=== MACRO_INVOCATION gold -> detected as CONDITIONAL_BLOCK: {len(cases_cond_as_macro)} ===")
    for c in cases_cond_as_macro:
        print(f"\n  {c['file']}: gold={c['gold']}, det={c['det']}")
        print(f"  SNIPPET:\n{c['snippet']}")

    print(f"\n=== CONDITIONAL_BLOCK gold -> detected as MACRO_INVOCATION: {len(cases_macro_as_cond)} ===")
    for c in cases_macro_as_cond:
        print(f"\n  {c['file']}: gold={c['gold']}, det={c['det']}")
        print(f"  SNIPPET:\n{c['snippet']}")

    print(f"\n=== MACRO_DEFINITION -> LOOP_BLOCK confusion: {len(cases_macrodef_as_loop)} ===")
    for c in cases_macrodef_as_loop:
        print(f"\n  {c['file']}: gold={c['gold']}, det={c['det']}")
        print(f"  SNIPPET:\n{c['snippet']}")

asyncio.run(main())
