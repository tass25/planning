"""Producer/consumer pipeline — wires StreamAgent → StateAgent via a queue.

Usage::

    from partition.streaming.pipeline import run_streaming_pipeline

    results = asyncio.run(run_streaming_pipeline(file_meta))
    # results: list[tuple[LineChunk, ParsingState]]
"""

from __future__ import annotations

import asyncio
from typing import Optional
from uuid import UUID

from partition.models.file_metadata import FileMetadata
from partition.streaming.backpressure import create_queue
from partition.streaming.models import LineChunk, ParsingState
from partition.streaming.state_agent import StateAgent
from partition.streaming.stream_agent import StreamAgent


async def run_streaming_pipeline(
    file_meta: FileMetadata,
    *,
    queue_maxsize: Optional[int] = None,
    trace_id: UUID | None = None,
) -> list[tuple[LineChunk, ParsingState]]:
    """Stream *file_meta* through StreamAgent → StateAgent.

    Parameters:
        file_meta: Metadata for the file to process.
        queue_maxsize: Override the automatic queue size (useful for tests).
        trace_id: Optional tracing UUID shared across both agents.

    Returns:
        A list of ``(LineChunk, ParsingState-snapshot)`` tuples in file order.
    """
    if queue_maxsize is not None:
        queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
    else:
        queue = create_queue(file_meta)

    stream = StreamAgent(queue=queue, trace_id=trace_id)
    state = StateAgent(trace_id=trace_id)

    results: list[tuple[LineChunk, ParsingState]] = []

    async def producer() -> None:
        await stream.process(file_meta)

    async def consumer() -> None:
        while True:
            chunk = await queue.get()
            if chunk is None:  # EOF sentinel
                queue.task_done()
                break
            parsing_state = await state.process(chunk)
            results.append((chunk, parsing_state.model_copy(deep=True)))
            queue.task_done()

    await asyncio.gather(producer(), consumer())
    return results
