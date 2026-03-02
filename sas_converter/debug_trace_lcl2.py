"""Trace chunks around L460-500 for gsh_11."""
import asyncio, hashlib
from pathlib import Path
from uuid import uuid4
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

async def main():
    sf = Path('knowledge_base/gold_standard/gsh_11_scoring_engine.sas')
    fm = make_fm(sf)
    pairs = await run_streaming_pipeline(fm)
    
    for chunk, state in pairs:
        if 460 <= chunk.line_number <= 510:
            bt = state.current_block_type
            lcl = state.last_content_line
            lcb = state.last_closed_block
            snippet = chunk.content[:80].replace('\n', '\\n')
            print(f"  L{chunk.line_number} bt={bt} lcl={lcl} | {snippet!r}")
            if lcb:
                print(f"       -> CLOSED: {lcb}")

asyncio.run(main())
