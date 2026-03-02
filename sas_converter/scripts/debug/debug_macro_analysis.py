"""
Comprehensive analysis of MACRO_DEFINITION misses.
- Runs the real pipeline to get detected blocks
- Classifies each gold MACRO_DEFINITION as whole-body or header-only
- Shows which ones are missed and which are correct
"""
import json, asyncio, hashlib, re
from pathlib import Path
from uuid import uuid4

import sys
sys.path.insert(0, str(Path(__file__).parent))

from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

MEND_RE = re.compile(r'^\s*%mend\b', re.I)

def is_whole_body(mb, lines, mend_lines):
    """Return True if gold block ends at %mend (tolerance=2)."""
    ge = mb['line_end']
    # Find nearest %mend after line_start
    m_start = mb['line_start']
    nearest = min((l for l in mend_lines if l >= m_start), default=None)
    return nearest is not None and abs(ge - nearest) <= 2

def _make_file_meta(sas_path):
    raw = sas_path.read_bytes()
    enc = "utf-8"
    try: raw.decode("utf-8")
    except UnicodeDecodeError: enc = "latin-1"
    return FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding=enc,
        content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
        line_count=raw.count(b"\n")+1, lark_valid=True)

async def main():
    gold_dir = Path('knowledge_base/gold_standard')
    TOLERANCE = 2

    total_whole = 0; total_header = 0
    missed_whole = 0; missed_header = 0
    correct_whole = 0; correct_header = 0
    
    misses = []

    for gf in sorted(gold_dir.glob("*.gold.json")):
        d = json.loads(gf.read_text())
        sas_path = gold_dir / (gf.stem.replace('.gold', '') + '.sas')
        if not sas_path.exists():
            continue
        lines = sas_path.read_text(encoding='latin-1').splitlines()
        mend_lines = {i for i, l in enumerate(lines, 1) if MEND_RE.match(l)}

        fm = _make_file_meta(sas_path)
        pairs = await run_streaming_pipeline(fm)
        det_events = BoundaryDetector().detect(pairs, fm.file_id)

        gold_macros = [b for b in d['blocks'] if b['partition_type'] == 'MACRO_DEFINITION']

        for mb in gold_macros:
            gs = mb['line_start']
            ge = mb['line_end']
            style = "whole-body" if is_whole_body(mb, lines, mend_lines) else "header-only"

            if style == "whole-body":
                total_whole += 1
            else:
                total_header += 1

            # Check if detected correctly
            found = any(
                ev.partition_type == "MACRO_DEFINITION"
                and abs(ev.line_start - gs) <= TOLERANCE
                and abs(ev.line_end - ge) <= TOLERANCE
                for ev in det_events
            )

            # Find closest detected macro
            macro_dets = [ev for ev in det_events if ev.partition_type == "MACRO_DEFINITION"]
            closest = min(macro_dets, key=lambda e: abs(e.line_start - gs), default=None)

            if found:
                if style == "whole-body":
                    correct_whole += 1
                else:
                    correct_header += 1
            else:
                if style == "whole-body":
                    missed_whole += 1
                else:
                    missed_header += 1
                c_str = f"→ det L{closest.line_start}-{closest.line_end}" if closest else "→ NONE"
                misses.append(f"  [{style:10s}] {gf.stem.replace('.gold',''):<35} gold L{gs}-{ge} {c_str}")

    print(f"\n=== MACRO_DEFINITION Miss Analysis ===")
    print(f"\nWhole-body macros: {total_whole} total, {correct_whole} correct, {missed_whole} missed")
    print(f"Header-only macros: {total_header} total, {correct_header} correct, {missed_header} missed")
    print(f"\nTotal correct: {correct_whole + correct_header} / {total_whole + total_header}")
    print(f"\n=== Missed blocks ===")
    for m in misses:
        print(m)
    
    print(f"\n=== Strategy Analysis ===")
    print(f"Current (MACRO in implicit close): correct={correct_whole+correct_header}")
    print(f"  - whole-body hits: {correct_whole}, header-only hits: {correct_header}")
    print(f"\nIf we REMOVE MACRO from implicit close (extend all to %mend):")
    print(f"  Expected: whole-body all correct ({total_whole}), header-only all missed ({total_header})")
    net_change = total_whole - missed_whole - correct_header
    print(f"  Net change vs current: {total_whole - missed_whole} - {correct_header} = {net_change}")
    print(f"  (We gain {total_whole - missed_whole} whole-body and lose {correct_header} header-only)")

asyncio.run(main())
