"""StreamingParser — Consolidated L2-B agent.

Merges StreamAgent + StateAgent into a single agent that wraps
``run_streaming_pipeline()``.  The internal producer/consumer queue
architecture is preserved for backpressure.
"""

from __future__ import annotations

from partition.base_agent import BaseAgent
from partition.models.file_metadata import FileMetadata
from partition.streaming.models import LineChunk, ParsingState
from partition.streaming.pipeline import run_streaming_pipeline


class StreamingParser(BaseAgent):
    """Consolidated streaming agent: reads SAS files and produces (chunk, state) pairs."""

    agent_name = "StreamingParser"

    async def process(  # type: ignore[override]
        self,
        file_meta: FileMetadata,
    ) -> list[tuple[LineChunk, ParsingState]]:
        """Stream a SAS file through the parser pipeline.

        Args:
            file_meta: Metadata for the file to process.

        Returns:
            List of (LineChunk, ParsingState) tuples in file order.
        """
        return await run_streaming_pipeline(file_meta, trace_id=self.trace_id)
