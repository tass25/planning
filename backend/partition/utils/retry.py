"""Retry utilities — rate limiter + circuit breaker for LLM API calls.

Complements ``base_agent.with_retry`` (exponential backoff decorator).

This module provides:
    RateLimitSemaphore — async semaphore for Azure OpenAI / Groq concurrency
    CircuitBreaker     — trip after N failures, auto-reset after cooldown

Migration note (Week 9):
    Azure OpenAI has higher rate limits than Groq (30 RPM free tier),
    but a semaphore is still needed for burst protection and to avoid
    429 Too Many Requests errors under heavy load.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import structlog

logger = structlog.get_logger()


class RateLimitSemaphore:
    """Async semaphore for LLM API concurrency control.

    Limits the number of concurrent LLM calls to prevent 429 errors.

    Usage::

        limiter = RateLimitSemaphore(max_concurrent=5)
        async with limiter:
            result = await llm_client.generate(prompt)

    Defaults:
        Azure OpenAI: max_concurrent=10 (generous limits with student tier)
        Groq:         max_concurrent=3  (30 RPM free tier, leave headroom)
    """

    def __init__(self, max_concurrent: int = 10):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max = max_concurrent
        self._active = 0

    async def __aenter__(self):
        await self._semaphore.acquire()
        self._active += 1
        return self

    async def __aexit__(self, *args):
        self._active -= 1
        self._semaphore.release()

    @property
    def active_calls(self) -> int:
        """Number of currently active LLM calls."""
        return self._active


class CircuitBreaker:
    """Circuit breaker for external service calls.

    Trips open after ``failure_threshold`` consecutive failures.
    Auto-resets after ``reset_timeout`` seconds (half-open → closed).

    States:
        CLOSED   — normal operation, calls pass through
        OPEN     — tripped, all calls fail-fast with CircuitOpenError
        HALF_OPEN — one probe call allowed; success → CLOSED, failure → OPEN

    Usage::

        breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60)
        if breaker.allow_request():
            try:
                result = await llm_call()
                breaker.record_success()
            except Exception:
                breaker.record_failure()
                raise
        else:
            # fail-fast or use fallback
            ...
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        name: str = "default",
    ):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.name = name

        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._success_count = 0

    @property
    def state(self) -> str:
        """Current circuit state."""
        if self._state == self.OPEN and self._last_failure_time:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.reset_timeout:
                self._state = self.HALF_OPEN
                logger.info(
                    "circuit_half_open",
                    breaker=self.name,
                    elapsed_s=round(elapsed, 1),
                )
        return self._state

    def allow_request(self) -> bool:
        """Check whether a request should be attempted."""
        state = self.state
        if state == self.CLOSED:
            return True
        if state == self.HALF_OPEN:
            return True  # allow one probe
        return False  # OPEN → fail-fast

    def record_success(self) -> None:
        """Record a successful call — reset failures, close circuit."""
        self._failure_count = 0
        self._success_count += 1
        if self._state == self.HALF_OPEN:
            self._state = self.CLOSED
            logger.info("circuit_closed", breaker=self.name)

    def record_failure(self) -> None:
        """Record a failed call — increment failures, possibly trip open."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._failure_count >= self.failure_threshold:
            self._state = self.OPEN
            logger.warning(
                "circuit_opened",
                breaker=self.name,
                failures=self._failure_count,
                reset_after_s=self.reset_timeout,
            )

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED."""
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        logger.info("circuit_reset", breaker=self.name)


# ── Global instances ──────────────────────────────────────────────────────────

# Azure OpenAI rate limiter (generous — student tier allows ~60 RPM)
azure_limiter = RateLimitSemaphore(max_concurrent=10)

# Groq fallback rate limiter (conservative — 30 RPM free tier)
groq_limiter = RateLimitSemaphore(max_concurrent=3)

# Circuit breakers per LLM provider
azure_breaker = CircuitBreaker(
    failure_threshold=5, reset_timeout=60.0, name="azure_openai"
)
groq_breaker = CircuitBreaker(
    failure_threshold=3, reset_timeout=120.0, name="groq"
)
