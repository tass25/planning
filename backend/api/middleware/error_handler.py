"""Global exception handler — returns consistent JSON errors, no raw tracebacks.

Usage in main.py:
    from api.middleware.error_handler import register_error_handlers
    register_error_handlers(app)
"""

from __future__ import annotations

import traceback

import structlog
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

log = structlog.get_logger("codara.errors")


def register_error_handlers(app: FastAPI) -> None:
    """Register global exception handlers on *app*."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        log.warning(
            "http_exception",
            path=str(request.url),
            method=request.method,
            status=exc.status_code,
            detail=exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": True, "code": exc.status_code, "detail": exc.detail},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        log.error(
            "unhandled_exception",
            path=str(request.url),
            method=request.method,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={"error": True, "code": 500, "detail": "Internal server error"},
        )
