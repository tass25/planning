"""RAPTOR clustering backend — GMMClusterer.

Euclidean GMM with soft assignment (τ=0.72).
Production-stable, no extra deps.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import structlog
from sklearn.mixture import GaussianMixture

logger = structlog.get_logger()


class GMMClusterer:
    """Cluster embeddings using a Gaussian Mixture Model.

    Key parameters (from cahier des charges):
    - k = √N (number of components, min 2)
    - τ = 0.72 (soft-assignment threshold)
    - BIC convergence: |BIC_t − BIC_{t-1}| < ε stops recursion

    GMM is preferred over K-Means because a SAS block can semantically belong
    to more than one cluster (e.g., a DATE_ARITHMETIC merge block belongs to
    both the date-handling and the merge-semantics clusters).  Soft assignment
    (τ = 0.72) supports this without block duplication.
    """

    TAU = 0.72  # Soft-assignment threshold
    BIC_EPSILON = 0.01  # BIC convergence threshold
    MAX_RETRIES = 3  # Retries on ConvergenceWarning

    def cluster(
        self,
        embeddings: np.ndarray,
        max_k: Optional[int] = None,
        random_state: int = 42,
    ) -> tuple[list[list[int]], float]:
        """Cluster embeddings using GMM with soft assignment.

        Args:
            embeddings: (N, 768) array of Nomic embeddings.
            max_k:       Override for k (default: √N, min 2).
            random_state: Seed for reproducibility.

        Returns:
            (clusters, bic) where ``clusters`` is a list of index-lists and
            ``bic`` is the BIC score for the best fit.
        """
        n_samples = len(embeddings)
        if n_samples == 0:
            return [], 0.0
        if n_samples == 1:
            return [[0]], 0.0

        k = max_k or max(2, int(math.sqrt(n_samples)))
        k = min(k, n_samples)  # k cannot exceed the number of samples

        logger.info("gmm_clustering", n_samples=n_samples, k=k, tau=self.TAU)

        gmm: Optional[GaussianMixture] = None
        for attempt in range(self.MAX_RETRIES):
            try:
                gmm = GaussianMixture(
                    n_components=k,
                    covariance_type="full",
                    random_state=random_state + attempt,
                    max_iter=200,
                    n_init=3,
                    reg_covar=1e-5,  # Prevent singular covariance matrices
                )
                gmm.fit(embeddings)
                break
            except Exception as exc:
                logger.warning("gmm_fit_retry", attempt=attempt + 1, error=str(exc))
                if attempt == self.MAX_RETRIES - 1:
                    logger.error("gmm_fit_failed", msg="Falling back to single cluster")
                    return [list(range(n_samples))], 0.0

        responsibilities = gmm.predict_proba(embeddings)  # (N, k)
        bic = gmm.bic(embeddings)

        clusters: dict[int, list[int]] = {c: [] for c in range(k)}
        for sample_idx in range(n_samples):
            assigned = False
            for cluster_idx in range(k):
                if responsibilities[sample_idx, cluster_idx] >= self.TAU:
                    clusters[cluster_idx].append(sample_idx)
                    assigned = True
            if not assigned:
                best = int(np.argmax(responsibilities[sample_idx]))
                clusters[best].append(sample_idx)

        result = [members for members in clusters.values() if members]

        logger.info(
            "gmm_clustered",
            n_clusters=len(result),
            bic=bic,
            sizes=[len(c) for c in result],
        )
        return result, bic

    def check_convergence(self, bic_prev: float, bic_curr: float) -> bool:
        """Return True when |BIC_t − BIC_{t−1}| < ε (recursion should stop)."""
        return abs(bic_curr - bic_prev) < self.BIC_EPSILON


def get_clusterer() -> GMMClusterer:
    """Return the production clusterer (GMMClusterer).

    HyperRAPTORClusterer (Poincaré ball / geoopt) was removed — it was
    never enabled in production and is no longer maintained.
    GMMClusterer covers all production use cases.
    """
    return GMMClusterer()
