"""Analyze MACRO_DEFINITION: implicit vs explicit close."""
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

# Temporary: remove MACRO_DEFINITION from implicit close by subclassing
import structlog as _sl
from partition.streaming import state_agent as _sa

# Monkey-patch: read _EXPLICIT_CLOSE_TRIGGERS
orig_process = _sa.StateAgent._check_close.__func__ if hasattr(_sa.StateAgent._check_close, '__func__') else None

async def main():
    # Check the gold: 
    # whole-body = gold ends at %mend (detected line is near a %mend)
    # header-only = gold ends right before a DATA/PROC/SQL
    
    whole_body_matched = []
    header_only_matched = []
    whole_body_missed = []
    header_only_missed = []

    from partition.streaming import state_agent
    
    for gf in sorted(GOLD_DIR.glob("*.gold.json")):
        with open(gf, encoding='utf-8') as f:
            gold = json.load(f)
        stem = Path(gold['file_path']).stem
        sf = GOLD_DIR / f"{stem}.sas"
        if not sf.exists():
            continue
        sf_path = sf
        
        # Read file lines for analysis
        try:
            raw = sf_path.read_bytes()
            enc = "utf-8"
            try: raw.decode("utf-8")
            except: enc = "latin-1"
            lines = raw.decode(enc, errors='replace').split('\n')
        except:
            continue
        
        fm = make_fm(sf_path)
        pairs = await run_streaming_pipeline(fm)
        events = BoundaryDetector().detect(pairs, fm.file_id)
        
        for gb in gold.get('blocks', []):
            gt = gb['partition_type']
            if gt != 'MACRO_DEFINITION':
                continue
            gs, ge = gb['line_start'], gb['line_end']
            
            # Is it whole-body or header-only?
            # Check if line at ge contains %mend
            end_line_text = lines[ge-1].strip().lower() if ge <= len(lines) else ''
            is_whole_body = '%mend' in end_line_text
            
            # Check if matched
            matched = any(
                ev.partition_type.value == 'MACRO_DEFINITION' and
                abs(ev.line_start - gs) <= TOLERANCE and
                abs(ev.line_end - ge) <= TOLERANCE
                for ev in events
            )
            
            label = "whole" if is_whole_body else "header"
            if matched:
                if is_whole_body:
                    whole_body_matched.append((stem, gs, ge))
                else:
                    header_only_matched.append((stem, gs, ge))
            else:
                if is_whole_body:
                    whole_body_missed.append((stem, gs, ge))
                else:
                    header_only_missed.append((stem, gs, ge))
    
    print(f"Whole-body macros (gold ends at %mend):")
    print(f"  Matched: {len(whole_body_matched)}")
    print(f"  Missed:  {len(whole_body_missed)}")
    print(f"\nHeader-only macros (gold ends before DATA/PROC/SQL):")
    print(f"  Matched: {len(header_only_matched)}")
    print(f"  Missed:  {len(header_only_missed)}")

asyncio.run(main())
