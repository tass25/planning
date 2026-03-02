"""Show CONDITIONAL_BLOCK/MACRO_INVOCATION type confusion cases."""
import asyncio, hashlib, json, logging
import structlog
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))

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
    for gf in sorted(GOLD_DIR.glob("*.gold.json")):
        with open(gf, encoding='utf-8') as f:
            gold = json.load(f)
        stem = Path(gold['file_path']).stem
        sf = GOLD_DIR / f"{stem}.sas"
        if not sf.exists():
            continue
        
        # Read file lines
        raw = sf.read_bytes()
        enc = "utf-8"
        try: raw.decode("utf-8")
        except: enc = "latin-1"
        lines = raw.decode(enc, errors='replace').split('\n')
        
        fm = make_fm(sf)
        pairs = await run_streaming_pipeline(fm)
        events = BoundaryDetector().detect(pairs, fm.file_id)
        
        for gb in gold.get('blocks', []):
            gt = gb['partition_type']
            gs, ge = gb['line_start'], gb['line_end']
            
            # Gold says MACRO_INVOCATION but we detect CONDITIONAL_BLOCK
            # OR gold says CONDITIONAL_BLOCK but we detect MACRO_INVOCATION
            if gt not in ('MACRO_INVOCATION', 'CONDITIONAL_BLOCK'):
                continue
            
            closest = min(events, key=lambda e: abs(e.line_start - gs), default=None)
            if closest is None:
                continue
            pred = closest.partition_type.value
            if pred == gt:
                continue  # correct type
            
            # Check confusion pair
            if (pred, gt) in [('CONDITIONAL_BLOCK', 'MACRO_INVOCATION'), ('MACRO_INVOCATION', 'CONDITIONAL_BLOCK')]:
                snippet = '\n'.join(lines[gs-1:min(gs+3, ge, len(lines))])
                print(f"\n  {stem}: gold={gt} L{gs}-{ge}, det={pred} L{closest.line_start}-{closest.line_end}")
                print(f"  SAS: {snippet[:200]!r}")

asyncio.run(main())
