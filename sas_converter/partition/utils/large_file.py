"""Large-file detection + memory guards for the partitioning pipeline.

Determines processing strategy based on file size and configures
memory-related environment variables at pipeline startup.

Thresholds from cahier des charges:
    Standard: < 10,000 lines — full pipeline, normal checkpointing
    Large:    10,000–50,000 lines — aggressive checkpointing (every 25 blocks)
    Huge:     > 50,000 lines — RAPTOR HIGH-only strategy, no LOW/MOD clustering
"""

from __future__ import annotations

import os
from typing import Optional

import structlog

logger = structlog.get_logger()

# ── Thresholds ────────────────────────────────────────────────────────────────

LARGE_FILE_LINE_THRESHOLD = 10_000
HUGE_FILE_LINE_THRESHOLD = 50_000
MEMORY_LIMIT_MB = 100


# ── File Size Strategy ────────────────────────────────────────────────────────

def detect_file_size_strategy(file_path: str) -> str:
    """Determine processing strategy based on file line count.

    Returns:
        ``"standard"`` — normal pipeline, checkpoint every 50 blocks
        ``"large"``    — aggressive checkpointing every 25 blocks
        ``"huge"``     — RAPTOR HIGH-only (skip LOW/MODERATE clustering)
    """
    try:
        with open(file_path, "r", errors="ignore") as f:
            line_count = sum(1 for _ in f)
    except OSError as exc:
        logger.warning("file_size_check_failed", path=file_path, error=str(exc))
        return "standard"

    if line_count > HUGE_FILE_LINE_THRESHOLD:
        logger.warning(
            "huge_file_detected",
            path=file_path,
            lines=line_count,
            strategy="RAPTOR-HIGH-only",
        )
        return "huge"
    elif line_count > LARGE_FILE_LINE_THRESHOLD:
        logger.info(
            "large_file_detected",
            path=file_path,
            lines=line_count,
            strategy="aggressive_checkpointing",
        )
        return "large"
    else:
        return "standard"


def checkpoint_interval(strategy: str) -> int:
    """Return checkpoint interval (blocks) for a given strategy.

    Args:
        strategy: One of ``"standard"``, ``"large"``, ``"huge"``.

    Returns:
        Number of blocks between checkpoints.
    """
    return {"standard": 50, "large": 25, "huge": 10}.get(strategy, 50)


# ── Memory Guards ─────────────────────────────────────────────────────────────

def configure_memory_guards() -> None:
    """Set environment variables for memory management.

    Call once at pipeline startup (in ``PartitionOrchestrator.__init__``).

    Configures:
        PYTORCH_CUDA_ALLOC_CONF — prevent CUDA memory fragmentation
        OMP_NUM_THREADS          — limit OpenMP parallelism (sentence-transformers)
    """
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:128")
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    logger.info(
        "memory_guards_configured",
        cuda_alloc="max_split_size_mb:128",
        omp_threads=4,
    )


class MemoryMonitor:
    """Track peak memory usage during processing.

    Uses ``psutil`` (optional) to read RSS. Falls back to a no-op
    if psutil is not installed.

    Usage::

        mon = MemoryMonitor()
        mon.check()          # -> current RSS in MB
        mon.assert_under_limit(100)  # warns if > 100 MB
        mon.peak_mb          # -> peak observed value
    """

    def __init__(self) -> None:
        self.peak_mb: float = 0.0
        self._psutil_available = False
        try:
            import psutil  # noqa: F401

            self._psutil_available = True
        except ImportError:
            logger.debug("psutil_not_available", msg="MemoryMonitor is no-op")

    def check(self) -> float:
        """Return current process memory usage in MB."""
        if not self._psutil_available:
            return 0.0
        import psutil

        mem_mb = psutil.Process().memory_info().rss / (1024 * 1024)
        self.peak_mb = max(self.peak_mb, mem_mb)
        return mem_mb

    def assert_under_limit(self, limit_mb: Optional[float] = None) -> bool:
        """Check memory and warn if over limit.

        Returns:
            ``True`` if under limit, ``False`` if over.
        """
        limit = limit_mb or MEMORY_LIMIT_MB
        current = self.check()
        if current > limit:
            logger.warning(
                "memory_limit_exceeded",
                current_mb=round(current, 1),
                limit_mb=limit,
                peak_mb=round(self.peak_mb, 1),
            )
            return False
        return True
