import asyncio, json, hashlib
from pathlib import Path
from uuid import uuid4
from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline
from collections import defaultdict

async def run():
    gold_dir = Path('knowledge_base/gold_standard')
    
    miss_by_type = defaultdict(lambda: {'count': 0, 'diffs': []})
    
    for gf in sorted(gold_dir.glob('gsh_*.gold.json')):
        with open(gf) as f:
            gold = json.load(f)
        stem = Path(gold['file_path']).stem
        
        sas_path = gold_dir / (stem + '.sas')
        if not sas_path.exists():
            continue
        
        raw = sas_path.read_bytes()
        enc = 'utf-8'
        try: raw.decode('utf-8')
        except: enc = 'latin-1'
        
        fm = FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding=enc,
            content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
            line_count=raw.count(b'\n')+1, lark_valid=True)
        pairs = await run_streaming_pipeline(fm)
        events = BoundaryDetector().detect(pairs, fm.file_id)
        
        gold_blocks = gold['blocks']
        for gb in gold_blocks:
            t = gb['partition_type']
            s = gb['line_start']
            e = gb['line_end']
            
            # Find best matching detected block
            best = None
            best_diff = float('inf')
            for ev in events:
                if ev.partition_type.value == t:
                    diff = abs(ev.line_start - s) + abs(ev.line_end - e)
                    if diff < best_diff:
                        best_diff = diff
                        best = ev
            
            matched = (best is not None and 
                       abs(best.line_start - s) <= 2 and 
                       abs(best.line_end - e) <= 2)
            
            if not matched:
                miss_by_type[t]['count'] += 1
                if best:
                    end_diff = best.line_end - e
                    miss_by_type[t]['diffs'].append(end_diff)
    
    print("Type                     miss  avg_end_diff  pct_neg4")
    print("-" * 60)
    for t in sorted(miss_by_type, key=lambda x: -miss_by_type[x]['count']):
        d = miss_by_type[t]
        diffs = d['diffs']
        avg = sum(diffs)/len(diffs) if diffs else 0
        neg4 = sum(1 for x in diffs if -5 <= x <= -3)
        print(f'{t:<25} {d["count"]:4d}  {avg:+8.1f}   {neg4} of {len(diffs)}')

asyncio.run(run())
