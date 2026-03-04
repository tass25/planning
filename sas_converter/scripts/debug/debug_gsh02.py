import asyncio, hashlib
from pathlib import Path
from uuid import uuid4
from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

GOLD_DIR = Path("knowledge_base/gold_standard")

async def run():
    sas_path = GOLD_DIR / "gsh_02_macro_framework.sas"
    raw = sas_path.read_bytes()
    enc = "utf-8"
    try: raw.decode("utf-8")
    except: enc = "latin-1"
    fm = FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding=enc,
        content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
        line_count=raw.count(b"\n")+1, lark_valid=True)
    pairs = await run_streaming_pipeline(fm)
    events = BoundaryDetector().detect(pairs, fm.file_id)
    lines = []
    lines.append("Events L195-230:")
    for e in events:
        if e.line_start <= 230 and e.line_end >= 195:
            lines.append(f"  {e.partition_type.value} L{e.line_start}-{e.line_end}")
    lines.append("\nAll CONDITIONAL events:")
    for e in events:
        if e.partition_type.value == "CONDITIONAL_BLOCK":
            lines.append(f"  COND L{e.line_start}-{e.line_end}")
    Path("dbg_gsh02.txt").write_text("\n".join(lines))

asyncio.run(run())
