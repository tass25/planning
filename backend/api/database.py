"""Backward-compat shim — real implementation lives in api.core.database."""
# MOVED to api/core/database.py — imports forwarded for non-breaking migration
from api.core.database import (  # noqa: F401
    ApiBase,
    UserRow,
    ConversionRow,
    ConversionStageRow,
    KBEntryRow,
    KBChangelogRow,
    AuditLogRow,
    CorrectionRow,
    NotificationRow,
    get_api_engine,
    init_api_db,
    get_api_session,
)
