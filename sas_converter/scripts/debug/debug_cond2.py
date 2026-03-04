import json, asyncio, hashlib
from pathlib import Path
from uuid import uuid4
from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

GOLD_DIR = Path("knowledge_base/gold_standard")

async def run():
    out = []
    for gf in sorted(GOLD_DIR.glob("gsh_*.gold.json")):
        gold = json.load(open(gf))
        stem = Path(gold["file_path"]).stem
        gold_blocks = [b for b in gold["blocks"] if b["partition_type"] == "CONDITIONAL_BLOCK"]
        if not gold_blocks:
            continue
        sas_path = GOLD_DIR / f"{stem}.sas"
        raw = sas_path.read_bytes()
        enc = "utf-8"
        try: raw.decode("utf-8")
        except: enc = "latin-1"
        fm = FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding=enc,
            content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
            line_count=raw.count(b"\n")+1, lark_valid=True)
        pairs = await run_streaming_pipeline(fm)
        events = BoundaryDetector().detect(pairs, fm.file_id)
        det = [e for e in events if e.partition_type.value == "CONDITIONAL_BLOCK"]
        
        for gb in gold_blocks:
            gs, ge = gb["line_start"], gb["line_end"]
            matched = any(abs(d.line_start-gs)<=2 and abs(d.line_end-ge)<=2 for d in det)
            if not matched:
                best = min(det, key=lambda d: abs(d.line_start-gs)+abs(d.line_end-ge), default=None)
                if best:
                    out.append(f"{stem}: gold L{gs}-{ge} -> det L{best.line_start}-{best.line_end} sd={best.line_start-gs:+d} ed={best.line_end-ge:+d}")
                else:
                    out.append(f"{stem}: gold L{gs}-{ge} -> NONE")
    
    Path("dbg_cond2.txt").write_text("\n".join(out))
    print(f"{len(out)} COND misses")
    for line in out:
        print(line)

asyncio.run(run())
