import json, asyncio, hashlib
from pathlib import Path
from uuid import uuid4
from collections import Counter
from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

GOLD_DIR = Path("knowledge_base/gold_standard")

async def run():
    out = []
    for gf in sorted(GOLD_DIR.glob("gsh_*.gold.json")):
        gold = json.load(open(gf))
        stem = Path(gold["file_path"]).stem
        gold_procs = [b for b in gold["blocks"] if b["partition_type"] == "PROC_BLOCK"]
        if not gold_procs:
            continue
        sas_path = GOLD_DIR / f"{stem}.sas"
        if not sas_path.exists():
            continue
        raw = sas_path.read_bytes()
        enc = "utf-8"
        try: raw.decode("utf-8")
        except: enc = "latin-1"
        fm = FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding=enc,
            content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
            line_count=raw.count(b"\n")+1, lark_valid=True)
        pairs = await run_streaming_pipeline(fm)
        events = BoundaryDetector().detect(pairs, fm.file_id)
        det_procs = [e for e in events if e.partition_type.value == "PROC_BLOCK"]
        
        for gp in gold_procs:
            gs, ge = gp["line_start"], gp["line_end"]
            matched = any(abs(d.line_start-gs)<=2 and abs(d.line_end-ge)<=2 for d in det_procs)
            if not matched:
                best = min(det_procs, key=lambda d: abs(d.line_start-gs)+abs(d.line_end-ge), default=None)
                if best:
                    out.append(f"{stem}: gold L{gs}-{ge} -> det L{best.line_start}-{best.line_end} sd={best.line_start-gs:+d} ed={best.line_end-ge:+d}")
                else:
                    out.append(f"{stem}: gold L{gs}-{ge} -> NONE")
    
    end_diffs = []
    for line in out:
        if "ed=" in line and "NONE" not in line:
            ed = int(line.split("ed=")[1].split(" ")[0].split("\n")[0])
            end_diffs.append(ed)
    
    Path("dbg_proc.txt").write_text("\n".join(out))
    print(f"Written {len(out)} PROC misses. End diff distribution:")
    ec = Counter(end_diffs)
    for v, c in ec.most_common(15):
        print(f"  ed={v:+d}: {c}")

asyncio.run(run())
