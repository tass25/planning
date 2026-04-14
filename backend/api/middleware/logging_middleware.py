"""Structured request/response logging middleware.

Logs every request with method, path, status code, and latency
using structlog for JSON-compatible output.
"""

from __future__ import annotations

import time

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

log = structlog.get_logger("codara.http")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log all HTTP requests with structured key=value fields."""

    async def dispatch(self, request: Request, call_next) -> Response:
        t0 = time.perf_counter()
        response: Response | None = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            latency_ms = (time.perf_counter() - t0) * 1000
            log.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=status_code,
                latency_ms=round(latency_ms, 2),
                client=request.client.host if request.client else "unknown",
            )
