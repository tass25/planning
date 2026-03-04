"""Comprehensive miss analysis after fixes."""
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
    
    type_correct = defaultdict(int)
    type_total = defaultdict(int)
    type_missed = defaultdict(list)
    type_mismatch = defaultdict(int)  # (det_type, gold_type)

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
            type_total[g_type] += 1
            matched = any(matches(g_type, g_start, g_end, dt, ds, de) for dt, ds, de in detected)
            if matched:
                type_correct[g_type] += 1
            else:
                end_delta = None
                start_delta = None
                closest = None
                min_dist = 999
                for dt, ds, de in detected:
                    dist = abs(ds - g_start)
                    if dist < min_dist:
                        min_dist = dist
                        closest = (dt, ds, de)
                        end_delta = de - g_end
                        start_delta = ds - g_start
                if closest:
                    type_mismatch[(closest[0], g_type)] += 1
                type_missed[g_type].append({
                    "file": sas_file.name,
                    "gold": (g_start, g_end),
                    "closest": closest,
                    "end_delta": end_delta,
                    "start_delta": start_delta,
                })

    print("=== Miss analysis ===")
    total_correct = sum(type_correct.values())
    total_all = sum(type_total.values())
    print(f"Overall: {total_correct}/{total_all} = {total_correct/total_all*100:.1f}%")
    print()
    
    for t in sorted(type_total.keys()):
        c = type_correct[t]
        n = type_total[t]
        missed = type_missed[t]
        if missed:
            deltas = [m["end_delta"] for m in missed if m["end_delta"] is not None]
            avg_delta = sum(deltas)/len(deltas) if deltas else None
            print(f"  {t:<25}: {c}/{n} correct, {n-c} missed, avg_end_delta={avg_delta:.1f}" if avg_delta is not None else f"  {t:<25}: {c}/{n} correct, {n-c} missed")
        else:
            print(f"  {t:<25}: {c}/{n} correct")
    
    print("\n=== Top type mismatches (det_type -> gold_type) ===")
    sorted_mismatch = sorted(type_mismatch.items(), key=lambda x: -x[1])
    for (det, gold), count in sorted_mismatch[:15]:
        print(f"  {det} -> {gold}: {count}x")

asyncio.run(main())
