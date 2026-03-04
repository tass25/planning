"""Trace last_content_line around gsh_11 L473-490."""
import asyncio, hashlib
from pathlib import Path
from uuid import uuid4
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline
from partition.streaming.state_agent import StateAgent
from partition.streaming.models import LineChunk

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
    
    # Re-run StateAgent manually to trace state
    agent = StateAgent()
    for chunk, _ in pairs:
        if 470 <= chunk.line_number <= 498:
            state_before = agent.state.model_copy(deep=True)
            await agent.process(chunk)
            state_after = agent.state
            lcl = state_after.last_content_line
            bt = state_after.current_block_type
            lcb = state_after.last_closed_block
            print(f"  L{chunk.line_number} bt={bt} lcl={lcl} lcb={lcb!r} | {chunk.content[:60].replace(chr(10), '\\n')!r}")

asyncio.run(main())
