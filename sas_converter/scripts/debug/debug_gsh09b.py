"""
Debug script: Compare gold vs detected for gsh_09
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from partition.chunking.boundary_detector import BoundaryDetector

gold_path = Path('knowledge_base/gold_standard/gsh_09_analytics_pipeline.gold.json')
sas_path  = Path('knowledge_base/gold_standard/gsh_09_analytics_pipeline.sas')

gold = json.loads(gold_path.read_text())
gold_blocks = gold['blocks']
sas_lines = sas_path.read_text(encoding='latin-1').splitlines()

det = BoundaryDetector()
det_blocks = det.detect(sas_lines, "gsh_09")

TOLERANCE = 2

def match_block(g, det_blocks, tol=2):
    g_type = g['partition_type']
    g_start = g['line_start']
    g_end   = g['line_end']
    for d in det_blocks:
        if d.partition_type == g_type:
            if abs(d.line_start - g_start) <= tol and abs(d.line_end - g_end) <= tol:
                return d
    return None

print(f"\n=== gsh_09 Gold vs Detected ===")
print(f"Gold: {len(gold_blocks)} blocks | Det: {len(det_blocks)} blocks")
correct = 0
for g in gold_blocks:
    m = match_block(g, det_blocks)
    ok = "OK" if m else "MISS"
    if m:
        correct += 1
    det_match = f"→ det L{m.line_start}-{m.line_end}" if m else "→ NO MATCH"
    print(f"  [{ok}] {g['partition_type']:25s} L{g['line_start']}-{g['line_end']:4d} {det_match}")

print(f"\nAccuracy: {correct}/{len(gold_blocks)} ({100*correct/len(gold_blocks):.1f}%)")

print("\n=== Detected blocks ===")
for d in det_blocks:
    print(f"  {d.partition_type:25s} L{d.line_start}-{d.line_end}")
