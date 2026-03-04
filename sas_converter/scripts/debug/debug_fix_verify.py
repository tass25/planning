"""Verify multi-line comment fix for gsh_11 around L473-560."""
import asyncio
from partition.streaming.pipeline import run_streaming_pipeline as run_pipeline
from partition.models.file_metadata import FileMetadata
from pathlib import Path

file_path = Path('knowledge_base/gold_standard/gsh_11_risk_premium.sas')
fm = FileMetadata(file_path=str(file_path), file_name=file_path.name, encoding='utf-8')
results = asyncio.run(run_pipeline(fm))

print('=== State transitions L460-570 ===')
for chunk, state in results:
    if 460 <= chunk.line_number <= 570:
        bt = state.current_block_type
        lc = state.last_closed_block
        parts = []
        if bt:
            parts.append(f'IN={bt}')
        if lc:
            parts.append(f'CLOSED={lc.block_type}@{lc.line_start}-{lc.line_end}')
        snippet = chunk.content[:70].replace('\n', '\\n')
        print(f'  L{chunk.line_number}: {"|".join(parts) or "---"} | {snippet!r}')
