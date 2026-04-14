"""RAPTORTreeBuilder — recursive RAPTOR tree construction for SAS files."""

from __future__ import annotations

import uuid
from typing import Optional

import numpy as np
import structlog

from partition.models.partition_ir import RAPTORNode, PartitionIR
from partition.raptor.embedder import NomicEmbedder
from partition.raptor.clustering import GMMClusterer
from partition.raptor.summarizer import ClusterSummarizer

logger = structlog.get_logger()


class RAPTORTreeBuilder:
    """Build a RAPTOR tree for a single SAS file.

    Algorithm (Sarthi et al., adapted for SAS code):
    1. Leaf nodes = PartitionIR blocks, embedded with Nomic Embed.
    2. GMM-cluster at level L → L+1 cluster nodes.
    3. Summarise each cluster (3-tier LLM fallback) → embed summary → RAPTORNode.
    4. Convergence check: stop when k=1, depth >= max_depth, or BIC converges.
    5. If not converged: recurse on L+1 nodes as new leaves.
    6. Final root node = whole-file summary.

    Dynamic depth:
    - Standard files:    max_depth = 3
    - Macro-heavy files: max_depth = 5 (macro_density > 0.4)
    """

    DEFAULT_MAX_DEPTH = 3
    MACRO_HEAVY_MAX_DEPTH = 5
    MACRO_DENSITY_THRESHOLD = 0.4

    def __init__(
        self,
        embedder: NomicEmbedder,
        clusterer: GMMClusterer,
        summarizer: ClusterSummarizer,
    ):
        self.embedder = embedder
        self.clusterer = clusterer
        self.summarizer = summarizer

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def build_tree(
        self,
        partitions: list[PartitionIR],
        file_id: str,
        macro_density: float = 0.0,
    ) -> list[RAPTORNode]:
        """Build the full RAPTOR tree for a file's partitions.

        Args:
            partitions:    All PartitionIR objects for this file.
            file_id:       UUID string of the source file.
            macro_density: Fraction of macro blocks (>0.4 triggers deep tree).

        Returns:
            All RAPTORNode objects in the tree (leaf + cluster + root).
        """
        max_depth = (
            self.MACRO_HEAVY_MAX_DEPTH
            if macro_density > self.MACRO_DENSITY_THRESHOLD
            else self.DEFAULT_MAX_DEPTH
        )

        logger.info(
            "raptor_tree_build_start",
            file_id=file_id,
            n_partitions=len(partitions),
            max_depth=max_depth,
            macro_density=macro_density,
        )

        all_nodes: list[RAPTORNode] = []

        # Level 0: leaf nodes
        leaf_nodes = self._create_leaf_nodes(partitions, file_id)
        all_nodes.extend(leaf_nodes)

        current_level_nodes = leaf_nodes
        prev_bic = float("inf")
        current_depth = 0

        while current_depth < max_depth:
            current_depth += 1

            if len(current_level_nodes) <= 1:
                logger.info("raptor_single_node_stop", depth=current_depth)
                break

            embeddings = np.array([n.embedding for n in current_level_nodes])
            clusters, bic = self.clusterer.cluster(embeddings)

            if self.clusterer.check_convergence(prev_bic, bic):
                logger.info(
                    "raptor_bic_converged",
                    depth=current_depth,
                    bic_prev=prev_bic,
                    bic_curr=bic,
                )
                break
            prev_bic = bic

            cluster_nodes: list[RAPTORNode] = []
            for cluster_idx, member_indices in enumerate(clusters):
                members = [current_level_nodes[i] for i in member_indices]
                cluster_node = self._create_cluster_node(
                    members=members,
                    level=current_depth,
                    cluster_label=cluster_idx,
                    file_id=file_id,
                )
                cluster_nodes.append(cluster_node)
                all_nodes.append(cluster_node)

            logger.info(
                "raptor_level_complete",
                depth=current_depth,
                n_clusters=len(cluster_nodes),
            )
            current_level_nodes = cluster_nodes

        # Root node
        if len(current_level_nodes) > 1:
            root = self._create_root_node(
                current_level_nodes, file_id, current_depth + 1
            )
            all_nodes.append(root)
        elif len(current_level_nodes) == 1:
            current_level_nodes[0].level = current_depth

        self._backlink_partitions(partitions, all_nodes)

        logger.info(
            "raptor_tree_complete",
            file_id=file_id,
            total_nodes=len(all_nodes),
            tree_depth=current_depth,
        )
        return all_nodes

    # ------------------------------------------------------------------
    # Internal node factories
    # ------------------------------------------------------------------

    def _create_leaf_nodes(
        self,
        partitions: list[PartitionIR],
        file_id: str,
    ) -> list[RAPTORNode]:
        """Create level-0 leaf nodes; one per PartitionIR block."""
        codes = [p.source_code for p in partitions]
        embeddings = self.embedder.embed_batch(codes)

        leaf_nodes: list[RAPTORNode] = []
        fid = uuid.UUID(file_id) if isinstance(file_id, str) else file_id
        for partition, embedding in zip(partitions, embeddings):
            node = RAPTORNode(
                node_id=uuid.uuid4(),
                level=0,
                summary=(
                    f"Leaf: {partition.partition_type.value} "
                    f"(lines {partition.line_start}–{partition.line_end})"
                ),
                summary_tier="skipped",
                embedding=embedding,
                child_ids=[],
                cluster_label=None,
                file_id=fid,
                partition_ids=[str(partition.block_id)],
            )
            leaf_nodes.append(node)
        return leaf_nodes

    def _create_cluster_node(
        self,
        members: list[RAPTORNode],
        level: int,
        cluster_label: int,
        file_id: str,
    ) -> RAPTORNode:
        """Create a cluster node by summarising and embedding its members."""
        all_partition_ids: list[str] = []
        code_blocks: list[str] = []
        for member in members:
            all_partition_ids.extend(member.partition_ids)
            code_blocks.append(member.summary)

        summary_obj, tier = self.summarizer.summarize(code_blocks)
        summary_embedding = self.embedder.embed(summary_obj.summary)
        fid = uuid.UUID(file_id) if isinstance(file_id, str) else file_id

        return RAPTORNode(
            node_id=uuid.uuid4(),
            level=level,
            summary=summary_obj.summary,
            summary_tier=tier,
            embedding=summary_embedding,
            child_ids=[str(m.node_id) for m in members],
            cluster_label=cluster_label,
            file_id=fid,
            partition_ids=all_partition_ids,
        )

    def _create_root_node(
        self,
        top_nodes: list[RAPTORNode],
        file_id: str,
        level: int,
    ) -> RAPTORNode:
        """Create the single root node summarising the entire file."""
        summaries = [n.summary for n in top_nodes]
        all_partition_ids: list[str] = []
        for n in top_nodes:
            all_partition_ids.extend(n.partition_ids)

        summary_obj, tier = self.summarizer.summarize(summaries)
        summary_embedding = self.embedder.embed(summary_obj.summary)
        fid = uuid.UUID(file_id) if isinstance(file_id, str) else file_id

        return RAPTORNode(
            node_id=uuid.uuid4(),
            level=level,
            summary=summary_obj.summary,
            summary_tier=tier,
            embedding=summary_embedding,
            child_ids=[str(n.node_id) for n in top_nodes],
            cluster_label=None,
            file_id=fid,
            partition_ids=all_partition_ids,
        )

    def _backlink_partitions(
        self,
        partitions: list[PartitionIR],
        all_nodes: list[RAPTORNode],
    ) -> None:
        """Populate raptor_leaf_id / raptor_cluster_id / raptor_root_id on each partition."""
        leaf_lookup: dict[str, RAPTORNode] = {
            node.partition_ids[0]: node
            for node in all_nodes
            if node.level == 0 and len(node.partition_ids) == 1
        }
        l1_clusters = [n for n in all_nodes if n.level == 1]
        root_node: Optional[RAPTORNode] = (
            max(all_nodes, key=lambda n: n.level) if all_nodes else None
        )

        for partition in partitions:
            pid = str(partition.block_id)

            if pid in leaf_lookup:
                partition.raptor_leaf_id = str(leaf_lookup[pid].node_id)

            for cluster in l1_clusters:
                if pid in cluster.partition_ids:
                    partition.raptor_cluster_id = str(cluster.node_id)
                    break

            if root_node:
                partition.raptor_root_id = str(root_node.node_id)
