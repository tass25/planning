"""ChunkingAgent — Consolidated L2-C agent.

Merges BoundaryDetectorAgent + PartitionBuilderAgent into a single agent:
detect boundaries → build PartitionIR objects in one ``process()`` call.
"""

from __future__ import annotations

from uuid import UUID

from partition.base_agent import BaseAgent
from partition.models.partition_ir import PartitionIR
from partition.streaming.models import LineChunk, ParsingState

from .boundary_detector import BoundaryDetectorAgent
from .partition_builder import PartitionBuilderAgent


class ChunkingAgent(BaseAgent):
    """Consolidated chunking agent: boundary detection + partition building."""

    agent_name = "ChunkingAgent"

    def __init__(self, trace_id: UUID | None = None) -> None:
        super().__init__(trace_id)
        self._boundary = BoundaryDetectorAgent(trace_id=self.trace_id)
        self._builder = PartitionBuilderAgent(trace_id=self.trace_id)

    async def process(  # type: ignore[override]
        self,
        chunks_with_states: list[tuple[LineChunk, ParsingState]],
        file_id: UUID,
    ) -> list[PartitionIR]:
        """Detect boundaries and build PartitionIR objects.

        Args:
            chunks_with_states: Output of the streaming pipeline.
            file_id: Source file UUID.

        Returns:
            List of PartitionIR objects ready for RAPTOR + complexity scoring.
        """
        events = await self._boundary.process(chunks_with_states, file_id)
        partitions = await self._builder.process(events)
        return partitions
