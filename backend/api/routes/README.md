# `api/routes/` — HTTP Route Handlers

Each file is a FastAPI router mounted under `/api`. Route handlers stay thin —
business logic lives in `api/services/` and `partition/`.

## Files

| File | Prefix | Key endpoints |
|------|--------|---------------|
| `auth.py` | `/api/auth` | POST /login, POST /register, POST /signup, GET /me, POST /github-callback |
| `conversions.py` | `/api/conversions` | POST /upload, POST /start, GET /{id}, GET /stream (SSE), download .py/.md/.html/.zip |
| `knowledge_base.py` | `/api/knowledge-base` | CRUD + GET /changelog |
| `admin.py` | `/api/admin` | Users, audit logs, system health, pipeline config, file registry |
| `analytics.py` | `/api/analytics` | Time-series conversion stats, failure mode breakdown |
| `notifications.py` | `/api/notifications` | List, mark read |
| `settings.py` | `/api/settings` | Profile update, email preferences |

## Conversion lifecycle

```
POST /upload          → saves file to Blob (or local disk), returns SasFile[]
POST /start           → creates ConversionRow + 8 ConversionStageRows, triggers pipeline
GET  /{id}            → polls current state (frontend calls this every 1.2s)
GET  /{id}/stream     → SSE alternative to polling (one persistent connection)
GET  /{id}/download/* → .py / .md / .html / .zip bundle
POST /{id}/corrections → stores human correction, feeds back into KB
```

## Access control

- `get_current_user` (JWT dependency) is applied to every route except `/auth/*`
- Admin endpoints check `current_user["role"] == "admin"` and return 403 otherwise
- Conversion ownership is checked via `_assert_owner()` — admins see everything,
  regular users only see their own conversions
