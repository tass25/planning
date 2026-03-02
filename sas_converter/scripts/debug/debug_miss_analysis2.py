"""Analyze remaining misses by type from the benchmark."""
import asyncio, hashlib, json, logging, os, sys
os.environ['STRUCTLOG_LEVEL'] = 'CRITICAL'
import structlog
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
)

from pathlib import Path
from uuid import uuid4
from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

def make_fm(p):
    raw = p.read_bytes()
    enc = "utf-8"
    try: raw.decode("utf-8")
    except UnicodeDecodeError: enc = "latin-1"
    return FileMetadata(
        file_id=uuid4(), file_path=str(p), encoding=enc,
        content_hash=hashlib.sha256(raw).hexdigest(),
        file_size_bytes=len(raw), line_count=raw.count(b"\n")+1, lark_valid=True
    )

GOLD_DIR = Path('knowledge_base/gold_standard')
TOLERANCE = 2

async def main():
    miss_by_type = {}
    ok_by_type = {}
    miss_details = []
    
    for gf in sorted(GOLD_DIR.glob("*.gold.json")):
        with open(gf, encoding='utf-8') as f:
            gold = json.load(f)
        
        stem = Path(gold['file_path']).stem
        sf = GOLD_DIR / f"{stem}.sas"
        if not sf.exists():
            continue
        
        fm = make_fm(sf)
        pairs = await run_streaming_pipeline(fm)
        events = BoundaryDetector().detect(pairs, fm.file_id)
        
        gold_blocks = gold.get('blocks', [])
        detected = [(ev.partition_type.value, ev.line_start, ev.line_end) for ev in events]
        
        for gb in gold_blocks:
            gt = gb['partition_type']
            gs = gb['line_start']
            ge = gb['line_end']
            matched = False
            for ptype, ds, de in detected:
                if ptype == gt and abs(ds-gs) <= TOLERANCE and abs(de-ge) <= TOLERANCE:
                    matched = True
                    break
            if matched:
                ok_by_type[gt] = ok_by_type.get(gt, 0) + 1
            else:
                miss_by_type[gt] = miss_by_type.get(gt, 0) + 1
                closest = min(events, key=lambda e: abs(e.line_start - gs), default=None)
                if closest:
                    miss_details.append({
                        'file': stem, 'type': gt, 'gold_s': gs, 'gold_e': ge,
                        'det_s': closest.line_start, 'det_e': closest.line_end,
                        'det_type': closest.partition_type.value,
                        'ds': closest.line_start - gs, 'de': closest.line_end - ge
                    })
                else:
                    miss_details.append({'file': stem, 'type': gt, 'gold_s': gs, 'gold_e': ge,
                                         'det_s': None, 'det_e': None, 'det_type': 'NONE', 'ds': 0, 'de': 0})

    print("=== Miss by type ===")
    all_types = set(list(miss_by_type.keys()) + list(ok_by_type.keys()))
    for t in sorted(all_types, key=lambda x: miss_by_type.get(x, 0), reverse=True):
        m = miss_by_type.get(t, 0)
        o = ok_by_type.get(t, 0)
        total = m + o
        print(f"  {t:<30} {o:>3}/{total:<3} correct, {m:>3} missed")
    
    print(f"\n  Total: {sum(ok_by_type.values())} correct, {sum(miss_by_type.values())} missed")
    
    print("\n=== Misses: same type detected (wrong boundaries), avg delta ===")
    from collections import defaultdict
    groupd = defaultdict(list)
    for m in miss_details:
        if m['det_type'] == m['type']:
            groupd[m['type']].append((m['ds'], m['de']))
    for t in sorted(groupd.keys(), key=lambda x: len(groupd[x]), reverse=True):
        pairs_list = groupd[t]
        n = len(pairs_list)
        avg_ds = sum(x[0] for x in pairs_list)/n
        avg_de = sum(x[1] for x in pairs_list)/n
        print(f"  {t:<30} n={n:>3} avg_start_delta={avg_ds:+.1f} avg_end_delta={avg_de:+.1f}")
    
    print("\n=== Type mismatches (predicted → gold) ===")
    from collections import Counter
    mistype = Counter((m['det_type'], m['type']) for m in miss_details if m['det_type'] != m['type'] and m['det_type'] != 'NONE')
    for (pred, gold_t), cnt in mistype.most_common(15):
        print(f"  {pred:<25} -> {gold_t:<25} ({cnt}x)")
    
    print("\n=== Undetected (no block found near gold start) ===")
    undet = [m for m in miss_details if m['det_type'] == 'NONE']
    print(f"  {len(undet)} undetected gold blocks")
    for m in undet[:10]:
        print(f"    {m['file']}: {m['type']} L{m['gold_s']}-{m['gold_e']}")

asyncio.run(main())
