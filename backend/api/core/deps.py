"""FastAPI dependency injection helpers.

# Pattern: Dependency Injection

All route handlers should use these dependencies via FastAPI's Depends()
instead of importing the engine directly from api.main (which creates
a circular import). Example usage:

    @router.get("/items")
    def list_items(
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_user),
    ):
        ...
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import structlog
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.core.auth import decode_token, security
from api.core.database import get_api_engine, get_api_session
from fastapi.security import HTTPAuthorizationCredentials

log = structlog.get_logger("codara.deps")

# ── Engine singleton ──────────────────────────────────────────────────────────

_engine = None


def _get_engine():
    """Return the SQLAlchemy engine singleton, initialised lazily."""
    global _engine
    if _engine is None:
        db_path = os.getenv(
            "SQLITE_PATH",
            str(Path(__file__).resolve().parent.parent.parent / "data" / "codara_api.db"),
        )
        _engine = get_api_engine(db_path)
    return _engine


# ── Database dependency ───────────────────────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy Session and close it after the request."""
    session = get_api_session(_get_engine())
    try:
        yield session
    finally:
        session.close()


# ── Auth dependencies ─────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """Extract and validate the current user from the JWT token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    return payload


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Raise 403 if the authenticated user is not an admin."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
