"""
Trace StateAgent processing for gsh_11 around L480-490
"""
import asyncio, hashlib, logging
from pathlib import Path
from uuid import uuid4
import sys
sys.path.insert(0, str(Path(__file__).parent))
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline
from partition.streaming.state_agent import StateAgent
from partition.streaming.models import ParsingState

async def main():
    sas_path = Path('knowledge_base/gold_standard/gsh_11_scoring_engine.sas')
    raw = sas_path.read_bytes()
    enc = "utf-8"
    try: raw.decode("utf-8")
    except UnicodeDecodeError: enc = "latin-1"
    fm = FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding=enc,
        content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
        line_count=raw.count(b"\n")+1, lark_valid=True)

    pairs = await run_streaming_pipeline(fm)
    
    # Replay StateAgent manually and trace around L480-490
    agent = StateAgent(trace_id=uuid4())
    print("=== Tracing L470-500 ===")
    for chunk, state in pairs:
        ln = chunk.line_number
        if ln < 473 or ln > 548:
            # Still process early pairs to build state
            agent.process(chunk, state)
            continue
        if ln >= 473:
            print(f"\nChunk L{ln}: {repr(chunk.content[:80])}")
            bt_before = agent.state.current_block_type
            new_state = agent.process(chunk, state)
            bt_after = agent.state.current_block_type
            lcb = agent.state.last_closed_block
            print(f"  before_bt={bt_before} -> after_bt={bt_after} | lcb={lcb}")
        if ln > 548:
            break

asyncio.run(main())
