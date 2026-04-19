# `api/core/` — Shared Infrastructure

Everything the route handlers rely on but don't own: authentication, database
models, Pydantic schemas, and data-access repositories.

## Files

| File | Purpose |
|------|---------|
| `auth.py` | JWT signing/verification (HS256, 24h expiry), bcrypt password hashing, `get_current_user` FastAPI dependency |
| `database.py` | SQLAlchemy ORM models + `get_api_engine()` / `get_api_session()` helpers |
| `schemas.py` | Pydantic v2 request/response models that match the TypeScript types in `frontend/src/types/index.ts` |
| `deps.py` | FastAPI `Depends()` helpers (lazy engine singleton, pagination params) |

## `database.py` models

| Model | Table | Notes |
|-------|-------|-------|
| `UserRow` | `users` | role: admin / user / viewer; hashed_password: bcrypt |
| `ConversionRow` | `conversions` | status: queued → running → completed / partial / failed |
| `ConversionStageRow` | `conversion_stages` | one row per pipeline stage; composite index on (conversion_id, stage) |
| `KBEntryRow` | `kb_entries` | SQL-side KB mirror; canonical store is LanceDB |
| `KBChangelogRow` | `kb_changelog` | CASCADE delete when parent KB entry is removed |
| `AuditLogRow` | `audit_logs` | LLM call audit; indexed by timestamp and model |
| `CorrectionRow` | `corrections` | Human corrections submitted via the UI |
| `NotificationRow` | `notifications` | Per-user; indexed by (user_id, read) for efficient unread counts |

## Auth flow

```
POST /api/auth/login
  → verify bcrypt hash
  → sign JWT (sub=user_id, role=role, exp=now+24h)
  → return token

GET /api/* (protected)
  → Authorization: Bearer <token>
  → get_current_user() dependency decodes + validates JWT
  → injects {"sub": user_id, "role": role} into route handler
```

## Why SQLite in WAL mode?

WAL (Write-Ahead Logging) allows concurrent reads while a write is in progress,
which matters because pipeline background threads write stage updates at the
same time the API serves SSE polling requests. Without WAL, those reads would
block behind the write lock.
