"""Debug MACRO_INVOCATION misses: detailed analysis."""
import sys, os, json, asyncio, hashlib
from pathlib import Path
from collections import Counter
sys.path.insert(0, ".")
os.environ.setdefault("GROQ_API_KEY", "none")

from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline
from uuid import uuid4

GOLD_DIR = Path("knowledge_base/gold_standard")

async def debug_macro_inv():
    misses = []
    
    for gf in sorted(GOLD_DIR.glob("gsh_*.gold.json")):
        with open(gf, encoding="utf-8") as f:
            gold_data = json.load(f)
        
        stem = Path(gold_data["file_path"]).stem
        gold_blocks = gold_data.get("blocks", [])
        gold_invs = [b for b in gold_blocks if b["partition_type"] == "MACRO_INVOCATION"]
        if not gold_invs:
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
        
        det_invs = [e for e in events if e.partition_type.value == "MACRO_INVOCATION"]
        
        for gb in gold_invs:
            gs_start = gb["line_start"]
            gs_end = gb["line_end"]
            
            matched = False
            for dg in det_invs:
                if abs(dg.line_start - gs_start) <= 2 and abs(dg.line_end - gs_end) <= 2:
                    matched = True
                    break
            
            if not matched:
                best = min(det_invs,
                    key=lambda dg: abs(dg.line_start - gs_start) + abs(dg.line_end - gs_end),
                    default=None)
                
                if best:
                    sd = best.line_start - gs_start
                    ed = best.line_end - gs_end
                    misses.append({
                        "file": stem,
                        "gold_start": gs_start,
                        "gold_end": gs_end,
                        "det_start": best.line_start,
                        "det_end": best.line_end,
                        "start_diff": sd,
                        "end_diff": ed,
                    })
                else:
                    misses.append({
                        "file": stem,
                        "gold_start": gs_start,
                        "gold_end": gs_end,
                        "det_start": None,
                        "det_end": None,
                        "start_diff": 9999,
                        "end_diff": 9999,
                    })
    
    print(f"\nMACRO_INVOCATION misses: {len(misses)}")
    print(f"\n{'File':<28} {'Gold':>10} {'Det':>10} {'StartDiff':>10} {'EndDiff':>10}")
    print("-" * 75)
    
    start_diffs = []
    end_diffs = []
    
    for m in sorted(misses, key=lambda x: (x['start_diff'], x['end_diff'])):
        det_str = f"{m['det_start']}-{m['det_end']}" if m["det_start"] else "NONE"
        gold_str = f"{m['gold_start']}-{m['gold_end']}"
        print(f"{m['file']:<28} {gold_str:>10} {det_str:>10} {m['start_diff']:>10} {m['end_diff']:>10}")
        if m["det_start"] is not None:
            start_diffs.append(m["start_diff"])
            end_diffs.append(m["end_diff"])
    
    if start_diffs:
        avg_s = sum(start_diffs) / len(start_diffs)
        avg_e = sum(end_diffs) / len(end_diffs)
        print(f"\nAvg start_diff: {avg_s:.1f}, avg end_diff: {avg_e:.1f}")
        
        sc = Counter(start_diffs)
        print("\nStart diff distribution (top 10):")
        for val, cnt in sc.most_common(10):
            print(f"  start_diff={val:+d}: {cnt}")
        
        ec = Counter(end_diffs)
        print("\nEnd diff distribution (top 10):")
        for val, cnt in ec.most_common(10):
            print(f"  end_diff={val:+d}: {cnt}")

asyncio.run(debug_macro_inv())
