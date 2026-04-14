"""Pipeline event system — Observer pattern for stage lifecycle events.

# Pattern: Observer

The PipelineEventEmitter decouples the orchestrator from its side effects
(SQLite writes, DuckDB audit logs, SSE broadcasting).  Adding Azure Event
Hubs later requires only a new listener, not touching orchestrator code.

Usage::

    emitter = PipelineEventEmitter()
    emitter.add_listener(SQLiteStageListener(engine))
    emitter.add_listener(DuckDBAuditListener(duckdb_path))

    await emitter.emit(StageEvent(
        conversion_id="conv-123",
        stage="translation",
        status="completed",
        latency_ms=1240.5,
    ))
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import structlog

log = structlog.get_logger("codara.events")


# ── Event model ───────────────────────────────────────────────────────────────


@dataclass
class StageEvent:
    """Emitted at stage start, completion, or failure."""

    conversion_id: str
    stage: str
    status: str                    # running | completed | failed | skipped
    latency_ms: float = 0.0
    retry_count: int = 0
    warnings: list[str] = field(default_factory=list)
    description: Optional[str] = None
    error: Optional[str] = None


# ── Listener interface ────────────────────────────────────────────────────────


class StageEventListener(ABC):
    """Abstract listener that reacts to stage lifecycle events."""

    @abstractmethod
    async def on_stage_event(self, event: StageEvent) -> None:
        """Handle a stage event. Must not raise — log and swallow errors."""


# ── Emitter ───────────────────────────────────────────────────────────────────


class PipelineEventEmitter:
    """Broadcast StageEvents to all registered listeners concurrently."""

    def __init__(self) -> None:
        self._listeners: list[StageEventListener] = []

    def add_listener(self, listener: StageEventListener) -> None:
        self._listeners.append(listener)

    async def emit(self, event: StageEvent) -> None:
        """Fan out the event to all listeners; errors are swallowed per-listener."""
        if not self._listeners:
            return
        tasks = [
            asyncio.create_task(_safe_notify(listener, event))
            for listener in self._listeners
        ]
        await asyncio.gather(*tasks)


async def _safe_notify(listener: StageEventListener, event: StageEvent) -> None:
    try:
        await listener.on_stage_event(event)
    except Exception as exc:
        log.error(
            "event_listener_error",
            listener=type(listener).__name__,
            stage=event.stage,
            error=str(exc),
        )
