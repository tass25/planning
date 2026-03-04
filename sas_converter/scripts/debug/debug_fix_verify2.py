"""Show ALL block open/close events for gsh_11."""
import asyncio
from partition.streaming.pipeline import run_streaming_pipeline as run_pipeline
from partition.models.file_metadata import FileMetadata
from pathlib import Path

file_path = Path('knowledge_base/gold_standard/gsh_11_risk_premium.sas')
fm = FileMetadata(file_path=str(file_path), file_name=file_path.name, encoding='utf-8')
results = asyncio.run(run_pipeline(fm))

prev_bt = None
for chunk, state in results:
    bt = state.current_block_type
    lc = state.last_closed_block
    if lc:
        print(f'  CLOSED {lc.block_type} L{lc.line_start}-{lc.line_end}  (at chunk L{chunk.line_number})')
    if bt != prev_bt:
        if bt not in (None, 'IDLE'):
            print(f'  OPEN   {bt} (at chunk L{chunk.line_number})')
        prev_bt = bt

total = len(results)
print(f'\nTotal chunks: {total}')
