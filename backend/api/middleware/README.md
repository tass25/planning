# `api/middleware/` — Request Middleware

## Files

| File | Purpose |
|------|---------|
| `logging_middleware.py` | Structured request logging via structlog — logs method, path, status code, and latency for every request |
| `error_handler.py` | Converts unhandled exceptions into consistent JSON error responses so the frontend always gets `{"detail": "..."}` instead of a raw 500 HTML page |

## Error response format

All errors (validation, auth, 404, unexpected exceptions) return the same shape:

```json
{
  "detail": "human-readable message"
}
```

HTTPException with a custom status code passes through unchanged.
Unhandled exceptions become 500 with a generic message — the real error
is logged via structlog so it shows up in Azure Monitor / local console.
