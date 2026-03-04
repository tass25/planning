import asyncio, hashlib
from pathlib import Path
from uuid import uuid4
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline

async def run():
    sas_path = Path('knowledge_base/gold_standard/gs_37_do_loop_list.sas')
    raw = sas_path.read_bytes()
    fm = FileMetadata(file_id=uuid4(), file_path=str(sas_path), encoding='utf-8',
        content_hash=hashlib.sha256(raw).hexdigest(), file_size_bytes=len(raw),
        line_count=raw.count(b'\n')+1, lark_valid=True)
    pairs = await run_streaming_pipeline(fm)
    for chunk, state in pairs[:15]:
        lines_in_chunk = chunk.content.count('\n') + 1
        content_preview = chunk.content.replace('\n', '|')[:70]
        print(f'L{chunk.line_number:3d} ({lines_in_chunk}L) bt={str(state.current_block_type):<22} | {content_preview}')

asyncio.run(run())
