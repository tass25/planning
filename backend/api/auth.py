"""Backward-compat shim — real implementation lives in api.core.auth."""
# MOVED to api/core/auth.py — imports forwarded for non-breaking migration
from api.core.auth import (  # noqa: F401
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    pwd_context,
    security,
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
    get_current_user,
)
