"""BaseAgent abstract class — foundation for all pipeline agents."""

from abc import ABC, abstractmethod
from uuid import uuid4, UUID
from functools import wraps
import asyncio

import structlog


def with_retry(max_retries: int = 3, base_delay: float = 1.0, fallback=None):
    """Decorator for async retry with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds (doubled each attempt).
        fallback: Optional callable returning a fallback value on exhaustion.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt == max_retries:
                        if fallback is not None:
                            return fallback(*args, **kwargs)
                        raise
                    delay = base_delay * (2 ** attempt)
                    logger = structlog.get_logger()
                    logger.warning(
                        "retry_attempt",
                        func=func.__qualname__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay=delay,
                        error=str(last_exc),
                    )
                    await asyncio.sleep(delay)
        return wrapper
    return decorator


class BaseAgent(ABC):
    """Abstract base class for all pipeline agents.

    Every agent has:
      - A ``trace_id`` (auto-generated UUID if not supplied).
      - A bound structlog logger tagged with the agent name + trace_id.
      - An abstract ``process()`` coroutine to override.
    """

    def __init__(self, trace_id: UUID | None = None):
        self.trace_id = trace_id or uuid4()
        self.logger = structlog.get_logger().bind(
            agent=self.agent_name,
            trace_id=str(self.trace_id),
        )

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Return a human-readable name for this agent."""
        ...

    @abstractmethod
    async def process(self, *args, **kwargs):
        """Execute the agent's main logic (must be overridden)."""
        ...
