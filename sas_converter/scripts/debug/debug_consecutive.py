import json
from pathlib import Path
gold_dir = Path('knowledge_base/gold_standard')
for gf in sorted(gold_dir.glob('gsh_*.gold.json')):
    gold = json.load(open(gf))
    blocks = gold['blocks']
    stem = Path(gold['file_path']).stem
    prev = None
    for b in blocks:
        pt = b['partition_type']
        if prev and pt == prev['partition_type'] and pt in ('PROC_BLOCK', 'DATA_STEP'):
            gap = b['line_start'] - prev['line_end']
            if gap <= 6:
                ls = prev['line_start']; le = prev['line_end']
                xs = b['line_start']; xe = b['line_end']
                print(f"{stem}: {pt} L{ls}-{le} -> L{xs}-{xe} gap={gap}")
        prev = b
