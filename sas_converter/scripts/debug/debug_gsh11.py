import asyncio, json, hashlib
from pathlib import Path
from uuid import uuid4
from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

async def run():
    gold_dir = Path('knowledge_base/gold_standard')
    fn = 'gsh_11_scoring_engine'
    
    with open(gold_dir / (fn + '.gold.json')) as f:
        gold = json.load(f)
    
    sas_path = gold_dir / (fn + '.sas')
    raw = sas_path.read_bytes()
    fm = FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding='utf-8',
        content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
        line_count=raw.count(b'\n')+1, lark_valid=True)
    pairs = await run_streaming_pipeline(fm)
    events = BoundaryDetector().detect(pairs, fm.file_id)
    
    gold_blocks = gold['blocks']
    print(f"{'Gold':<35} {'Detected':<35} {'Match'}")
    print("-" * 80)
    
    for gb in gold_blocks:
        t = gb['partition_type']
        s = gb['line_start']
        e = gb['line_end']
        
        # Find best match
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
        
        gold_str = f"{t} {s}-{e}"
        if best:
            det_str = f"{best.partition_type.value} {best.line_start}-{best.line_end}"
            diff_str = f"d=({best.line_start-s:+d},{best.line_end-e:+d})"
        else:
            det_str = "NOT FOUND"
            diff_str = ""
        
        status = "[OK]" if matched else "[XX]"
        print(f"{status} {gold_str:<33} {det_str:<33} {diff_str}")

asyncio.run(run())
