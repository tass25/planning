import asyncio, hashlib
from pathlib import Path
from uuid import uuid4
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
    
    # Show all chunks around L200-220
    lines = ["Chunks around L200-220:"]
    for chunk, state in pairs:
        if 198 <= chunk.line_number <= 225:
            lines.append(f"L{chunk.line_number} [{state.current_block_type}] -> {repr(chunk.content[:100])}")
    Path("dbg_chunks02.txt").write_text("\n".join(lines))

asyncio.run(run())
