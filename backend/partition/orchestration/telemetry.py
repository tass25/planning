"""Azure Application Insights telemetry integration.

Initialises the OpenTelemetry-based Azure Monitor exporter once, then
exposes lightweight helpers that any module can call without importing
the full Azure SDK.

Graceful degradation: if the connection string is missing or the SDK is
not installed, every public function becomes a silent no-op.

Configuration
-------------
Set ``APPLICATIONINSIGHTS_CONNECTION_STRING`` in your ``.env`` file.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Optional

import structlog

logger = structlog.get_logger()

# ── Module-level state ────────────────────────────────────────────────
_initialised: bool = False
_tc = None  # TelemetryClient-like object (AzureMonitor envelope sender)
_tracer = None  # OpenTelemetry tracer
_meter = None  # OpenTelemetry meter


def _init_once() -> None:
    """Bootstrap Azure Monitor + OpenTelemetry (idempotent)."""
    global _initialised, _tc, _tracer, _meter  # noqa: PLW0603

    if _initialised:
        return
    _initialised = True

    # Prefer settings singleton; fall back to raw env var so telemetry.py
    # stays importable from partition/ without a circular dependency on api/.
    try:
        from config.settings import settings as _s
        conn_str = _s.applicationinsights_connection_string
    except Exception:
        conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "")

    if not conn_str:
        logger.info("telemetry_disabled", reason="no connection string — set APPLICATIONINSIGHTS_CONNECTION_STRING")
        return

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry import trace, metrics

        configure_azure_monitor(connection_string=conn_str)

        _tracer = trace.get_tracer("codara.pipeline")
        _meter  = metrics.get_meter("codara.pipeline")
        logger.info("telemetry_enabled", backend="azure_monitor")
    except Exception as exc:
        logger.warning("telemetry_init_failed", error=str(exc))


# ── Public API ────────────────────────────────────────────────────────

def track_event(
    name: str,
    properties: Optional[dict[str, str]] = None,
    measurements: Optional[dict[str, float]] = None,
) -> None:
    """Send a custom event to Application Insights.

    No-op when telemetry is disabled.
    """
    _init_once()
    if _tracer is None:
        return
    try:
        with _tracer.start_as_current_span(name) as span:
            for k, v in (properties or {}).items():
                span.set_attribute(k, v)
            for k, v in (measurements or {}).items():
                span.set_attribute(k, v)
    except Exception as exc:
        logger.debug("track_event_failed", event=name, error=str(exc))


def track_metric(
    name: str,
    value: float,
    dimensions: Optional[dict[str, str]] = None,
) -> None:
    """Record a custom metric value.

    No-op when telemetry is disabled.
    """
    _init_once()
    if _meter is None:
        return
    try:
        # Use a histogram — compatible with all OTel 1.x versions.
        # For point-in-time metrics, a single-bucket histogram records the value.
        histogram = _meter.create_histogram(name)
        histogram.record(value, attributes=dimensions or {})
    except Exception as exc:
        logger.debug("track_metric_failed", metric=name, error=str(exc))


@contextmanager
def trace_span(name: str, attributes: Optional[dict[str, str]] = None):
    """Context manager that creates an OpenTelemetry span.

    Measures wall-clock duration and records it as an attribute.
    No-op when telemetry is disabled.
    """
    _init_once()
    if _tracer is None:
        yield
        return
    try:
        with _tracer.start_as_current_span(name) as span:
            for k, v in (attributes or {}).items():
                span.set_attribute(k, v)
            t0 = time.perf_counter()
            yield span
            span.set_attribute("duration_ms", (time.perf_counter() - t0) * 1000)
    except Exception:
        yield
