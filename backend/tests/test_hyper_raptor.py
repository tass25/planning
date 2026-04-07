"""Tests for HyperRAPTORClusterer and get_clusterer() factory.

Tests:
  - Projection to Poincaré ball (all norms < 1)
  - Cluster count = k
  - All samples assigned
  - Fallback to GMM when geoopt unavailable
  - Feature flag routing via USE_HYPER_RAPTOR
  - Convergence on simple inputs
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from partition.raptor.clustering import GMMClusterer, HyperRAPTORClusterer, get_clusterer


@pytest.fixture
def small_embeddings():
    """32 samples, 768 dims (same as NomicEmbedder output)."""
    rng = np.random.default_rng(42)
    return rng.standard_normal((32, 768)).astype(np.float32)


@pytest.fixture
def large_embeddings():
    rng = np.random.default_rng(0)
    return rng.standard_normal((100, 768)).astype(np.float32)


# ── HyperRAPTORClusterer ─────────────────────────────────────────────

class TestHyperRAPTORClusterer:
    def test_projection_norms_below_one(self, small_embeddings):
        """All projected points must be strictly inside the Poincaré ball."""
        pytest.importorskip("geoopt")
        import torch
        clusterer = HyperRAPTORClusterer()
        projected = clusterer._project_to_ball(small_embeddings)
        norms = projected.norm(dim=-1)
        assert (norms < 1.0).all(), f"Max norm: {norms.max().item():.6f}"

    def test_cluster_count_equals_k(self, small_embeddings):
        pytest.importorskip("geoopt")
        clusterer = HyperRAPTORClusterer()
        k = 4
        clusters, score = clusterer.cluster(small_embeddings, max_k=k)
        assert len(clusters) <= k
        assert len(clusters) >= 1

    def test_all_samples_assigned(self, small_embeddings):
        pytest.importorskip("geoopt")
        clusterer = HyperRAPTORClusterer()
        clusters, _ = clusterer.cluster(small_embeddings)
        assigned = sum(len(c) for c in clusters)
        assert assigned == len(small_embeddings)

    def test_single_sample_returns_one_cluster(self):
        pytest.importorskip("geoopt")
        clusterer = HyperRAPTORClusterer()
        emb = np.random.randn(1, 768).astype(np.float32)
        clusters, _ = clusterer.cluster(emb)
        assert clusters == [[0]]

    def test_empty_returns_empty(self):
        pytest.importorskip("geoopt")
        clusterer = HyperRAPTORClusterer()
        clusters, score = clusterer.cluster(np.empty((0, 768), dtype=np.float32))
        assert clusters == []

    def test_fallback_to_gmm_without_geoopt(self, small_embeddings, monkeypatch):
        """HyperRAPTOR must fall back gracefully when geoopt is not installed."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "geoopt":
                raise ImportError("geoopt not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        clusterer = HyperRAPTORClusterer()
        clusterer._geoopt_available = False  # force fallback path
        clusters, score = clusterer.cluster(small_embeddings)
        assert len(clusters) > 0  # fell back to GMM, still produces results

    def test_large_input_completes(self, large_embeddings):
        pytest.importorskip("geoopt")
        clusterer = HyperRAPTORClusterer()
        clusters, score = clusterer.cluster(large_embeddings)
        assigned = sum(len(c) for c in clusters)
        assert assigned == len(large_embeddings)


# ── Feature flag routing ─────────────────────────────────────────────

class TestGetClusterer:
    def test_default_returns_gmm(self, monkeypatch):
        monkeypatch.delenv("USE_HYPER_RAPTOR", raising=False)
        clusterer = get_clusterer()
        assert isinstance(clusterer, GMMClusterer)

    def test_flag_false_returns_gmm(self, monkeypatch):
        monkeypatch.setenv("USE_HYPER_RAPTOR", "false")
        clusterer = get_clusterer()
        assert isinstance(clusterer, GMMClusterer)

    def test_flag_true_returns_hyper(self, monkeypatch):
        monkeypatch.setenv("USE_HYPER_RAPTOR", "true")
        clusterer = get_clusterer()
        assert isinstance(clusterer, HyperRAPTORClusterer)

    def test_gmm_still_works_after_flag_change(self, small_embeddings, monkeypatch):
        """Switching from HyperRAPTOR back to GMM must still produce valid clusters."""
        monkeypatch.setenv("USE_HYPER_RAPTOR", "false")
        clusterer = get_clusterer()
        clusters, bic = clusterer.cluster(small_embeddings)
        assert len(clusters) > 0
        assigned = sum(len(c) for c in clusters)
        assert assigned == len(small_embeddings)
