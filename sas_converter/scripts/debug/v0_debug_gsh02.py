"""Trace gsh_02 chunks around L393-412."""
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
    sas_file = GOLD_DIR / "gsh_02_macro_framework.sas"
    fm = make_meta(sas_file)
    pairs = await run_streaming_pipeline(fm)

    print("=== Chunks from streaming pipeline (L390-415) ===")
    for chunk, state in pairs:
        ln = chunk.line_number
        content = chunk.content
        lines_in = content.split("\n")
        start_ln = ln - len(lines_in) + 1
        if start_ln > 415 or ln < 390:
            continue
        print(f"\n  Chunk line_number={ln}, start_ln={start_ln}")
        print(f"  current_block_type={state.current_block_type}")
        print(f"  last_closed_block={state.last_closed_block}")
        print(f"  pending_block_start={state.pending_block_start}")
        print(f"  block_start_line={state.block_start_line}")
        for i, l in enumerate(lines_in):
            print(f"    [{start_ln + i}] {l[:70]}")

asyncio.run(main())
