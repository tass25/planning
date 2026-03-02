import asyncio, hashlib
from pathlib import Path
from uuid import uuid4
from partition.chunking.boundary_detector import BoundaryDetector
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

async def run():
    sas_path = Path('knowledge_base/gold_standard/gsh_10_financial_recon.sas')
    raw = sas_path.read_bytes()
    fm = FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding='utf-8',
        content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
        line_count=raw.count(b'\x0a')+1, lark_valid=True)
    pairs = await run_streaming_pipeline(fm)
    events = BoundaryDetector().detect(pairs, fm.file_id)
    lines = ["All events L725-760:"]
    for e in events:
        if (e.line_start <= 760 and e.line_end >= 725):
            lines.append(f"  {e.partition_type.value} L{e.line_start}-{e.line_end}")
    Path("debug_gsh10_out.txt").write_text("\n".join(lines))

asyncio.run(run())
