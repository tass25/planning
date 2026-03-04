"""Check what chunks the streaming pipeline produces for gsm_17 L148-165."""
import asyncio, hashlib, logging, sys
from pathlib import Path
from uuid import uuid4

import structlog
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))

sys.path.insert(0, "C:/Users/labou/Desktop/Stage/sas_converter")

from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

GOLD_DIR = Path("C:/Users/labou/Desktop/Stage/sas_converter/knowledge_base/gold_standard")

def make_meta(sas_path):
    raw = sas_path.read_bytes()
    enc = "utf-8"
    try: raw.decode("utf-8")
    except UnicodeDecodeError: enc = "latin-1"
    return FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding=enc,
        content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
        line_count=raw.count(b"\n")+1, lark_valid=True)

async def main():
    sas_file = GOLD_DIR / "gsm_17_etl_incremental.sas"
    fm = make_meta(sas_file)
    pairs = await run_streaming_pipeline(fm)

    print("=== Chunks from streaming pipeline (L145-175) ===")
    for chunk, state in pairs:
        ln = chunk.line_number
        content = chunk.content
        lines_in = content.split("\n")
        start_ln = ln - len(lines_in) + 1
        if start_ln > 175 or ln < 145:
            continue
        print(f"\n  Chunk line_number={ln}, start_ln={start_ln}")
        print(f"  current_block_type={state.current_block_type}")
        print(f"  last_closed_block={state.last_closed_block}")
        print(f"  pending_block_start={state.pending_block_start}")
        print(f"  block_start_line={state.block_start_line}")
        # Show content (truncated)
        for i, l in enumerate(lines_in):
            actual_ln = start_ln + i
            print(f"    [{actual_ln}] {l[:80]}")

asyncio.run(main())
