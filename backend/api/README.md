# backend/api — FastAPI Application

## Purpose
HTTP layer of the Codara platform. Handles authentication, conversion lifecycle,
knowledge-base CRUD, admin operations, analytics, and SSE streaming.

## Structure

```
api/
├── main.py              — FastAPI app: CORS, routers, seed data, /api/health
├── core/
│   ├── auth.py          — JWT (HS256), bcrypt, get_current_user dependency
│   ├── database.py      — SQLAlchemy ORM models + engine/session helpers
│   ├── deps.py          — FastAPI Depends() helpers (get_db lazy singleton)
│   ├── schemas.py       — Pydantic v2 request/response schemas
│   └── repositories/    — Data-access objects (ConversionRepository, etc.)
├── middleware/
│   ├── error_handler.py     — Global exception → JSON error response
│   └── logging_middleware.py — Structured request logging (structlog)
├── routes/
│   ├── auth.py          — POST /api/auth/login|register, GET /api/auth/me
│   ├── conversions.py   — Upload, start, poll, download, SSE, corrections
│   ├── knowledge_base.py — KB CRUD + changelog
│   ├── admin.py         — Admin-only: users, audit logs, system health
│   ├── analytics.py     — Conversion stats time-series
│   ├── notifications.py — User notification CRUD
│   └── settings.py      — Profile + preferences update
└── services/
    ├── conversion_service.py  — conv_to_out(), STAGES, STAGE_DISPLAY_MAP
    ├── pipeline_service.py    — run_pipeline_sync() background task
    └── translation_service.py — translate_sas_to_python() LLM fallback chain
```

## Config
All settings come from `config.settings.Settings` (Pydantic BaseSettings).
Never use `os.getenv()` directly inside `api/` — always `from config.settings import settings`.

Named constants (token limits, timeouts, SSE params) live in `config.constants`.

## Running
```bash
cd backend
uvicorn api.main:app --reload --port 8000
```

## Default seeded credentials
On first boot, random passwords are generated and printed once to stdout.
Pin them with env vars so they survive restarts:

| Role  | Email               | Env var                  |
|-------|---------------------|--------------------------|
| Admin | admin@codara.dev    | `CODARA_ADMIN_PASSWORD`  |
| User  | user@codara.dev     | `CODARA_USER_PASSWORD`   |

If the env var is absent, a fresh random password is generated and logged to stdout on each cold start.
