"""StreamAgent (#4) — Async line-by-line SAS file reader with backpressure.

Reads a SAS file asynchronously, coalesces continuation lines (no trailing
semicolon) into full logical statements, and pushes ``LineChunk`` objects
into an ``asyncio.Queue``.  Backpressure is enforced by the queue's
``maxsize``: when the consumer cannot keep up the producer blocks on
``queue.put()``.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import aiofiles

from partition.base_agent import BaseAgent
from partition.models.file_metadata import FileMetadata
from partition.streaming.models import LineChunk


class StreamAgent(BaseAgent):
    """Async streaming producer for SAS source files.

    Parameters:
        queue: The backpressure-bounded ``asyncio.Queue`` to write into.
        trace_id: Optional UUID for distributed tracing.
    """

    agent_name = "StreamAgent"

    def __init__(self, queue: asyncio.Queue, trace_id: UUID | None = None):
        super().__init__(trace_id)
        self.queue = queue

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def process(self, file_meta: FileMetadata) -> None:  # type: ignore[override]
        """Stream *file_meta* line-by-line into ``self.queue``.

        At EOF a ``None`` sentinel is pushed so the consumer knows
        the file is finished.
        """

        self.logger.info(
            "streaming_start",
            file=file_meta.file_path,
            encoding=file_meta.encoding,
            size_bytes=file_meta.file_size_bytes,
        )

        line_num = 0
        byte_offset = 0
        buffer = ""

        async with aiofiles.open(
            file_meta.file_path,
            mode="r",
            encoding=file_meta.encoding,
        ) as fh:
            async for raw_line in fh:
                line_num += 1
                byte_offset += len(raw_line.encode(file_meta.encoding))
                buffer += raw_line

                # A SAS statement ends when the line contains a semicolon
                if ";" in raw_line:
                    chunk = LineChunk(
                        file_id=file_meta.file_id,
                        line_number=line_num,
                        content=buffer.strip(),
                        byte_offset=byte_offset,
                        is_continuation=False,
                    )
                    await self.queue.put(chunk)
                    buffer = ""

        # Flush anything left in the buffer (unterminated statement)
        if buffer.strip():
            chunk = LineChunk(
                file_id=file_meta.file_id,
                line_number=line_num,
                content=buffer.strip(),
                byte_offset=byte_offset,
                is_continuation=True,
            )
            await self.queue.put(chunk)

        # EOF sentinel
        await self.queue.put(None)
        self.logger.info("streaming_complete", lines=line_num, bytes=byte_offset)
