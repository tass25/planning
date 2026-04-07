"""RAPTOR clustering backends.

Two implementations, selected via USE_HYPER_RAPTOR env var:

  GMMClusterer (default)
    Euclidean GMM with soft assignment (τ=0.72).
    Production-stable, no extra deps.

  HyperRAPTORClusterer (USE_HYPER_RAPTOR=true)
    Poincaré ball K-means via geoopt.
    Exploits the hierarchical tree structure of SAS code:
    parents (macros) cluster near the ball origin, leaves
    (DATA steps, PROC blocks) on the boundary.
    Requires: pip install geoopt>=0.5.0

Academic reference:
  Nickel & Kiela, "Poincaré Embeddings for Learning Hierarchical
  Representations", NeurIPS 2017.
"""

from __future__ import annotations

import math
import os
from typing import Optional

import numpy as np
from sklearn.mixture import GaussianMixture
import structlog

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

    TAU = 0.72          # Soft-assignment threshold
    BIC_EPSILON = 0.01  # BIC convergence threshold
    MAX_RETRIES = 3     # Retries on ConvergenceWarning

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
        k = min(k, n_samples)   # k cannot exceed the number of samples

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


# ── HyperRAPTOR — Poincaré ball K-means ─────────────────────────────

class HyperRAPTORClusterer:
    """Poincaré ball K-means clustering for hierarchical SAS code.

    Algorithm:
      1. Project Nomic 768-dim Euclidean vectors onto the Poincaré ball
         using the exponential map: x → tanh(‖x‖/2) · x/‖x‖
      2. Run Riemannian K-means on the Poincaré ball (geoopt)
      3. Assign each block to its nearest centroid (Poincaré distance)

    Why hyperbolic:
      SAS macro hierarchies are trees. Trees embed with zero distortion
      in hyperbolic space but require exponentially growing dimensions
      in Euclidean space (Sarkar 2011).  The Poincaré ball model
      (curvature c=−1) is numerically stable and GPU-friendly via geoopt.

    Fallback:
      If geoopt is not installed, falls back to GMMClusterer and logs
      a warning.  This keeps the pipeline working without the extra dep.
    """

    CURVATURE = 1.0       # Poincaré ball curvature |c|
    MAX_ITER = 100        # K-means iterations
    TOL = 1e-6            # convergence tolerance on centroid movement
    CLIP_NORM = 0.97      # keep points inside the ball (norm < 1)

    def __init__(self) -> None:
        self._geoopt_available: Optional[bool] = None

    def _check_geoopt(self) -> bool:
        if self._geoopt_available is None:
            try:
                import geoopt  # noqa: F401
                self._geoopt_available = True
            except ImportError:
                self._geoopt_available = False
                logger.warning(
                    "hyper_raptor_unavailable",
                    reason="geoopt not installed",
                    fallback="GMMClusterer",
                    fix="pip install geoopt>=0.5.0",
                )
        return self._geoopt_available

    def _project_to_ball(self, embeddings: np.ndarray) -> "torch.Tensor":
        """Map Euclidean vectors to the Poincaré ball via exponential map."""
        import torch

        x = torch.tensor(embeddings, dtype=torch.float32)
        # Normalise to unit sphere then scale by tanh(‖x‖/2)
        norms = x.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        scale = torch.tanh(norms / 2)
        projected = scale * (x / norms)
        # Numerical safety: keep strictly inside the ball
        proj_norms = projected.norm(dim=-1, keepdim=True)
        projected = projected / proj_norms.clamp(min=1e-8) * proj_norms.clamp(max=self.CLIP_NORM)
        return projected

    def _poincare_distance(self, u: "torch.Tensor", v: "torch.Tensor") -> "torch.Tensor":
        """Poincaré ball distance: d(u,v) = 2·arctanh(‖−u⊕v‖)."""
        import torch

        # Möbius addition: −u ⊕ v
        uu = (u * u).sum(dim=-1, keepdim=True)
        vv = (v * v).sum(dim=-1, keepdim=True)
        uv = (u * v).sum(dim=-1, keepdim=True)
        num = (1 - 2 * uv + vv) * u - (1 - uu) * v  # − (numerator of −u⊕v)
        # actually use closed form: ‖−u⊕v‖²
        numerator = (1 - 2 * uv + vv) ** 2 * uu
        denominator_sq = (1 - uu) ** 2 * (1 - 2 * uv + vv + vv * uu)
        # Safer: use geoopt distance
        import geoopt
        ball = geoopt.PoincareBall(c=self.CURVATURE)
        return ball.dist(u, v)

    def _frechet_mean(self, points: "torch.Tensor", weights: Optional["torch.Tensor"] = None) -> "torch.Tensor":
        """Fréchet mean on the Poincaré ball (iterative)."""
        import geoopt
        import torch

        ball = geoopt.PoincareBall(c=self.CURVATURE)
        # Initialise at weighted Euclidean mean, then project
        if weights is not None:
            mean_init = (points * weights.unsqueeze(-1)).sum(dim=0) / weights.sum()
        else:
            mean_init = points.mean(dim=0)
        norms = mean_init.norm()
        if norms >= 1.0:
            mean_init = mean_init / norms * self.CLIP_NORM

        mu = mean_init.clone()
        for _ in range(20):  # Riemannian gradient steps
            logs = ball.logmap(mu, points)           # log map at mu
            grad = -logs.mean(dim=0)                 # Riemannian gradient
            mu = ball.expmap(mu, -0.1 * grad)        # Riemannian SGD step
            mu_norm = mu.norm()
            if mu_norm >= 1.0:
                mu = mu / mu_norm * self.CLIP_NORM
        return mu

    def cluster(
        self,
        embeddings: np.ndarray,
        max_k: Optional[int] = None,
        random_state: int = 42,
    ) -> tuple[list[list[int]], float]:
        """Cluster using Poincaré K-means. Falls back to GMM if geoopt missing."""
        if not self._check_geoopt():
            return GMMClusterer().cluster(embeddings, max_k=max_k, random_state=random_state)

        import torch
        import geoopt

        n = len(embeddings)
        if n == 0:
            return [], 0.0
        if n == 1:
            return [[0]], 0.0

        k = max_k or max(2, int(math.sqrt(n)))
        k = min(k, n)

        logger.info("hyper_raptor_clustering", n_samples=n, k=k, curvature=self.CURVATURE)

        # Project to Poincaré ball
        torch.manual_seed(random_state)
        points = self._project_to_ball(embeddings)  # (N, 768)
        ball = geoopt.PoincareBall(c=self.CURVATURE)

        # Initialise centroids via K-means++ (Euclidean initialisation)
        idx = torch.randint(0, n, (1,)).item()
        centroids = [points[idx]]
        for _ in range(k - 1):
            # Distance to nearest centroid
            dists = torch.stack([ball.dist(points, c.unsqueeze(0).expand_as(points)).min(dim=-1).values
                                  for c in centroids], dim=1).min(dim=1).values
            probs = dists ** 2
            probs = probs / probs.sum()
            next_idx = torch.multinomial(probs, 1).item()
            centroids.append(points[next_idx])
        centroids = torch.stack(centroids)  # (k, 768)

        # Riemannian K-means iterations
        labels = torch.zeros(n, dtype=torch.long)
        for iteration in range(self.MAX_ITER):
            # Assignment step: Poincaré distance to each centroid
            dist_matrix = torch.stack([
                ball.dist(points, centroids[j].unsqueeze(0).expand(n, -1))
                for j in range(k)
            ], dim=1)  # (N, k)
            new_labels = dist_matrix.argmin(dim=1)

            # Update step: Fréchet mean per cluster
            new_centroids = []
            for j in range(k):
                members = (new_labels == j).nonzero(as_tuple=True)[0]
                if len(members) == 0:
                    new_centroids.append(centroids[j])
                else:
                    new_centroids.append(self._frechet_mean(points[members]))
            new_centroids = torch.stack(new_centroids)

            # Convergence check
            centroid_shift = ball.dist(new_centroids, centroids).max().item()
            centroids = new_centroids
            labels = new_labels

            if centroid_shift < self.TOL:
                logger.info("hyper_raptor_converged", iteration=iteration)
                break

        # Build cluster lists
        clusters: dict[int, list[int]] = {j: [] for j in range(k)}
        for i, label in enumerate(labels.tolist()):
            clusters[label].append(i)

        result = [members for members in clusters.values() if members]

        # Pseudo-BIC: sum of within-cluster Poincaré distances (lower = better)
        inertia = sum(
            ball.dist(
                points[members],
                centroids[j].unsqueeze(0).expand(len(members), -1),
            ).sum().item()
            for j, members in enumerate(clusters.values()) if members
        )

        logger.info(
            "hyper_raptor_clustered",
            n_clusters=len(result),
            inertia=f"{inertia:.4f}",
            sizes=[len(c) for c in result],
        )
        return result, -inertia  # negative inertia as BIC-compatible score

    def check_convergence(self, bic_prev: float, bic_curr: float) -> bool:
        """Return True when inertia improvement drops below ε."""
        return abs(bic_curr - bic_prev) < 0.01


def get_clusterer():
    """Return the appropriate clusterer based on USE_HYPER_RAPTOR env var."""
    if os.getenv("USE_HYPER_RAPTOR", "false").lower() == "true":
        return HyperRAPTORClusterer()
    return GMMClusterer()
