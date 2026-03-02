"""
Inspect the chunks produced by the streaming pipeline around L480-490
"""
import asyncio, hashlib
from pathlib import Path
from uuid import uuid4
import sys
sys.path.insert(0, str(Path(__file__).parent))
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

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
    
    print("=== Chunks around L473-495 (showing line_number and content) ===")
    for chunk, state in pairs:
        ln = chunk.line_number
        if 473 <= ln <= 500:
            print(f"\nChunk L{ln}: {repr(chunk.content[:120])}")

asyncio.run(main())
