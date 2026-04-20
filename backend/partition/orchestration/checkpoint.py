"""Redis-based checkpoint manager for fault-tolerant pipeline processing.

Key format : partition:{file_id}:checkpoint:{block_num}
TTL        : 24 hours
Frequency  : every 50 processed blocks
Degraded   : if Redis is unavailable, logs a warning and continues
"""

from __future__ import annotations

import json
from typing import Optional

import structlog

logger = structlog.get_logger()


class RedisCheckpointManager:
    """Save / restore pipeline checkpoints in Redis.

    On startup the manager pings Redis.  If the connection fails the
    ``available`` flag is set to ``False`` and every public method
    becomes a safe no-op (degraded mode).
    """

    CHECKPOINT_INTERVAL = 50  # blocks between checkpoints
    TTL_SECONDS = 86400  # 24 hours

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.available = False
        self.client = None
        try:
            import redis as _redis

            self.client = _redis.from_url(redis_url, decode_responses=True)
            self.client.ping()
            self.available = True
            logger.info("redis_connected", url=redis_url)
        except Exception as exc:
            self.client = None
            logger.warning(
                "redis_unavailable",
                msg="Continuing in degraded mode (no checkpointing)",
                error=str(exc),
            )

    # ------------------------------------------------------------------ save
    def save_checkpoint(
        self,
        file_id: str,
        block_num: int,
        partition_data: list[dict],
    ) -> bool:
        """Persist a checkpoint.  Only fires every *CHECKPOINT_INTERVAL* blocks.

        Returns ``True`` when a checkpoint was actually written.
        """
        if not self.available:
            return False

        if block_num > 0 and block_num % self.CHECKPOINT_INTERVAL != 0:
            return False

        key = f"partition:{file_id}:checkpoint:{block_num}"
        try:
            payload = json.dumps(
                {
                    "file_id": file_id,
                    "block_num": block_num,
                    "partition_count": len(partition_data),
                    "partitions": partition_data,
                }
            )
            self.client.setex(key, self.TTL_SECONDS, payload)
            logger.info(
                "checkpoint_saved",
                file_id=file_id,
                block=block_num,
                partitions=len(partition_data),
            )
            return True
        except Exception as exc:
            logger.warning("checkpoint_save_failed", file_id=file_id, error=str(exc))
            return False

    # -------------------------------------------------------------- find
    def find_latest_checkpoint(self, file_id: str) -> Optional[dict]:
        """Return the most recent checkpoint for *file_id*, or ``None``."""
        if not self.available:
            return None

        try:
            pattern = f"partition:{file_id}:checkpoint:*"
            keys = list(self.client.scan_iter(pattern))
            if not keys:
                return None

            latest_key = max(keys, key=lambda k: int(k.split(":")[-1]))
            data = self.client.get(latest_key)
            if data:
                checkpoint = json.loads(data)
                logger.info(
                    "checkpoint_found",
                    file_id=file_id,
                    block=checkpoint["block_num"],
                )
                return checkpoint
        except Exception as exc:
            logger.warning("checkpoint_scan_failed", file_id=file_id, error=str(exc))
        return None

    # -------------------------------------------------------------- clear
    def clear_checkpoints(self, file_id: str) -> None:
        """Remove all checkpoints for a completed file."""
        if not self.available:
            return

        try:
            pattern = f"partition:{file_id}:checkpoint:*"
            keys = list(self.client.scan_iter(pattern))
            if keys:
                self.client.delete(*keys)
                logger.info("checkpoints_cleared", file_id=file_id, count=len(keys))
        except Exception as exc:
            logger.warning("checkpoint_clear_failed", file_id=file_id, error=str(exc))
