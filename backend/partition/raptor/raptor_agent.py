"""RAPTORPartitionAgent — Agent #7: RAPTOR semantic clustering orchestrator."""

from __future__ import annotations

from uuid import UUID

from partition.base_agent import BaseAgent
from partition.models.partition_ir import PartitionIR
from partition.models.raptor_node import RAPTORNode
from partition.raptor.embedder import NomicEmbedder
from partition.raptor.clustering import GMMClusterer
from partition.raptor.summarizer import ClusterSummarizer
from partition.raptor.tree_builder import RAPTORTreeBuilder


class RAPTORPartitionAgent(BaseAgent):
    """Agent #7 — RAPTOR semantic clustering.

    Orchestrates:
        NomicEmbedder → GMMClusterer → ClusterSummarizer → RAPTORTreeBuilder

    for each file's partition set, producing a hierarchical RAPTOR tree
    stored as ``list[RAPTORNode]``.
    """

    agent_name = "RAPTORPartitionAgent"

    def __init__(self, trace_id=None, device: str = "cpu"):
        super().__init__(trace_id)

        self.embedder = NomicEmbedder(device=device)
        self.clusterer = GMMClusterer()
        self.summarizer = ClusterSummarizer()
        self.tree_builder = RAPTORTreeBuilder(
            embedder=self.embedder,
            clusterer=self.clusterer,
            summarizer=self.summarizer,
        )

    async def process(
        self,
        partitions: list[PartitionIR],
        file_id: str,
    ) -> list[RAPTORNode]:
        """Build a RAPTOR tree for one file's partitions.

        Args:
            partitions: All PartitionIR objects for the file.
            file_id:    Source file UUID string.

        Returns:
            All RAPTORNode objects (leaf + cluster + root).
        """
        if not partitions:
            self.logger.warning("raptor_no_partitions", file_id=file_id)
            return []

        macro_density = (
            sum(1 for p in partitions if p.has_macros) / len(partitions)
        )

        self.logger.info(
            "raptor_agent_start",
            file_id=file_id,
            n_partitions=len(partitions),
            macro_density=macro_density,
        )

        try:
            nodes = self.tree_builder.build_tree(
                partitions=partitions,
                file_id=file_id,
                macro_density=macro_density,
            )
            self.logger.info(
                "raptor_agent_complete",
                file_id=file_id,
                total_nodes=len(nodes),
                leaf_count=sum(1 for n in nodes if n.level == 0),
                cluster_count=sum(1 for n in nodes if n.level > 0),
            )
            return nodes

        except Exception as exc:
            self.logger.error(
                "raptor_agent_failed",
                file_id=file_id,
                error=str(exc),
            )
            # Graceful degradation: flat (leaf-only) tree
            return self.tree_builder._create_leaf_nodes(partitions, file_id)
