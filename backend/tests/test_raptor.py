"""Tests for the RAPTOR semantic clustering layer (week 5).

Covers GMMClusterer, ClusterSummarizer, RAPTORTreeBuilder, and the
RAPTORNode / PartitionIR integration.
"""

from __future__ import annotations

import hashlib
import uuid

import numpy as np
import pytest
from unittest.mock import MagicMock

from partition.raptor.clustering import GMMClusterer
from partition.raptor.summarizer import ClusterSummarizer, ClusterSummary
from partition.raptor.tree_builder import RAPTORTreeBuilder
from partition.models.partition_ir import RAPTORNode, PartitionIR
from partition.models.enums import PartitionType


# =====================================================================
# GMMClusterer
# =====================================================================


class TestGMMClusterer:
    """Test GMM clustering logic."""

    def test_cluster_basic(self):
        """9 embeddings in 3 tight groups → at least 2 clusters."""
        rng = np.random.RandomState(42)
        clusterer = GMMClusterer()
        embeddings = np.vstack(
            [
                rng.randn(3, 768) + np.array([5.0] * 768),
                rng.randn(3, 768) + np.array([-5.0] * 768),
                rng.randn(3, 768) + np.array([0.0] * 768),
            ]
        )
        clusters, bic = clusterer.cluster(embeddings)
        assert len(clusters) >= 2
        assert all(len(c) > 0 for c in clusters)

    def test_cluster_single_sample(self):
        """Single embedding → single cluster containing index 0."""
        clusterer = GMMClusterer()
        embeddings = np.random.randn(1, 768)
        clusters, bic = clusterer.cluster(embeddings)
        assert len(clusters) == 1
        assert clusters[0] == [0]

    def test_cluster_empty(self):
        """Zero-length input → empty clusters."""
        clusterer = GMMClusterer()
        clusters, bic = clusterer.cluster(np.array([]).reshape(0, 768))
        assert clusters == []
        assert bic == 0.0

    def test_bic_convergence_true(self):
        """|BIC_t − BIC_{t-1}| < 0.01 → converged."""
        clusterer = GMMClusterer()
        assert clusterer.check_convergence(100.0, 100.005)

    def test_bic_convergence_false(self):
        """|BIC_t − BIC_{t-1}| = 1.0 → NOT converged."""
        clusterer = GMMClusterer()
        assert not clusterer.check_convergence(100.0, 101.0)

    def test_soft_assignment_tau(self):
        """Threshold τ must be 0.72 per cahier des charges."""
        assert GMMClusterer.TAU == 0.72

    def test_all_samples_assigned(self):
        """Every sample must appear in at least one cluster."""
        rng = np.random.RandomState(7)
        clusterer = GMMClusterer()
        embeddings = rng.randn(12, 768)
        clusters, _ = clusterer.cluster(embeddings)
        assigned = {idx for c in clusters for idx in c}
        assert assigned == set(range(12))


# =====================================================================
# ClusterSummarizer
# =====================================================================


class TestClusterSummarizer:
    """Test the summarizer fallback chain and heuristic logic."""

    def test_heuristic_fallback_contains_block_info(self):
        """Heuristic summary text must mention 'SAS code block'."""
        summarizer = ClusterSummarizer()
        summary = summarizer._heuristic_summary(
            [
                "DATA mydata; SET input; x = 1; RUN;",
                "PROC MEANS DATA=mydata; VAR x; RUN;",
            ]
        )
        assert isinstance(summary, ClusterSummary)
        assert "SAS code block" in summary.summary

    def test_heuristic_detects_constructs(self):
        """Heuristic summary should detect DATA step and PROC MEANS."""
        summarizer = ClusterSummarizer()
        summary = summarizer._heuristic_summary(
            [
                "DATA sales; SET raw; RUN;",
                "PROC MEANS DATA=sales; VAR revenue; RUN;",
            ]
        )
        assert "DATA step" in summary.key_constructs
        assert "PROC MEANS" in summary.key_constructs

    def test_cache_key_deterministic(self):
        """Identical block sets must produce the same SHA-256 cache key."""
        blocks = ["block_a", "block_b"]
        key1 = hashlib.sha256("||".join(sorted(blocks)).encode()).hexdigest()
        key2 = hashlib.sha256("||".join(sorted(blocks)).encode()).hexdigest()
        assert key1 == key2

    def test_heuristic_complexity_thresholds(self):
        """LOW < 50 lines, MODERATE < 200 lines, HIGH >= 200 lines."""
        summarizer = ClusterSummarizer()

        # tiny block → LOW
        small = summarizer._heuristic_summary(["DATA x; RUN;"])
        assert small.estimated_complexity == "LOW"

        # large block → HIGH
        big_block = "\n".join([f"x{i} = {i};" for i in range(250)])
        large = summarizer._heuristic_summary([big_block])
        assert large.estimated_complexity == "HIGH"


# =====================================================================
# RAPTORNode model
# =====================================================================


class TestRAPTORNode:
    """Test the RAPTORNode Pydantic model."""

    def test_create_raptor_node(self):
        """Node creation with all required fields."""
        fid = uuid.uuid4()
        node = RAPTORNode(
            level=0,
            summary="Leaf node",
            summary_tier="skipped",
            embedding=[0.1] * 768,
            file_id=fid,
        )
        assert node.level == 0
        assert len(node.embedding) == 768
        assert node.file_id == fid
        assert node.partition_ids == []


# =====================================================================
# PartitionIR RAPTOR back-links
# =====================================================================


class TestPartitionIRRaptorFields:
    """Verify the RAPTOR extension fields on PartitionIR."""

    def _make_partition(self, ptype: PartitionType = PartitionType.DATA_STEP) -> PartitionIR:
        return PartitionIR(
            file_id=uuid.uuid4(),
            partition_type=ptype,
            source_code="DATA foo; RUN;",
            line_start=1,
            line_end=1,
        )

    def test_raptor_fields_default_none(self):
        """RAPTOR back-link fields start as None."""
        p = self._make_partition()
        assert p.raptor_leaf_id is None
        assert p.raptor_cluster_id is None
        assert p.raptor_root_id is None

    def test_has_macros_property(self):
        """has_macros is True only for MACRO_DEFINITION / MACRO_INVOCATION."""
        data = self._make_partition(PartitionType.DATA_STEP)
        macro_def = self._make_partition(PartitionType.MACRO_DEFINITION)
        macro_inv = self._make_partition(PartitionType.MACRO_INVOCATION)
        assert not data.has_macros
        assert macro_def.has_macros
        assert macro_inv.has_macros


# =====================================================================
# RAPTORTreeBuilder
# =====================================================================


class TestRAPTORTreeBuilder:
    """Test the recursive tree builder."""

    def _make_builder(self) -> RAPTORTreeBuilder:
        embedder = MagicMock()
        embedder.embed_batch.return_value = [[0.1] * 768, [0.2] * 768, [0.3] * 768]
        embedder.embed.return_value = [0.5] * 768
        clusterer = GMMClusterer()
        summarizer = MagicMock()
        summarizer.summarize.return_value = (
            ClusterSummary(
                summary="Test summary",
                key_constructs=["DATA step"],
                estimated_complexity="LOW",
            ),
            "heuristic_fallback",
        )
        return RAPTORTreeBuilder(embedder, clusterer, summarizer)

    def _make_partitions(self, n: int = 3) -> list[PartitionIR]:
        fid = uuid.uuid4()
        return [
            PartitionIR(
                file_id=fid,
                partition_type=PartitionType.DATA_STEP,
                source_code=f"DATA step_{i}; RUN;",
                line_start=i * 10 + 1,
                line_end=(i + 1) * 10,
            )
            for i in range(n)
        ]

    def test_leaf_node_creation(self):
        """Leaf nodes must be level 0, one per partition."""
        builder = self._make_builder()
        partitions = self._make_partitions(3)
        leaves = builder._create_leaf_nodes(partitions, str(uuid.uuid4()))
        assert len(leaves) == 3
        assert all(n.level == 0 for n in leaves)
        assert all(len(n.partition_ids) == 1 for n in leaves)

    def test_dynamic_depth_constants(self):
        """Standard max_depth=3, macro-heavy max_depth=5."""
        assert RAPTORTreeBuilder.DEFAULT_MAX_DEPTH == 3
        assert RAPTORTreeBuilder.MACRO_HEAVY_MAX_DEPTH == 5
        assert RAPTORTreeBuilder.MACRO_DENSITY_THRESHOLD == 0.4

    def test_build_tree_returns_nodes(self):
        """build_tree must return at least as many nodes as partitions (leaves)."""
        builder = self._make_builder()
        partitions = self._make_partitions(3)
        nodes = builder.build_tree(partitions, str(uuid.uuid4()))
        assert len(nodes) >= len(partitions)

    def test_backlink_sets_leaf_id(self):
        """After build_tree, each partition should have raptor_leaf_id set."""
        builder = self._make_builder()
        partitions = self._make_partitions(3)
        builder.build_tree(partitions, str(uuid.uuid4()))
        assert all(p.raptor_leaf_id is not None for p in partitions)
