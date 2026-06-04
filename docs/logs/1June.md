# 1 June 2026

## Session — Bug Fixes (continued from 31 May)

### Admin Notifications Fix
- AdminLayout bell icon was purely decorative — no fetch, no dropdown, no state
- Added full notification system matching UserLayout: `useUserStore` hooks, `fetchNotifications` on mount + 30s interval, animated dropdown with mark-read/mark-all-read
- **Files**: `frontend/src/components/layout/AdminLayout.tsx`

### Zip Upload Fix
- Frontend accepted `.zip` files but backend rejected anything not `.sas` (line 82 hard check)
- Rewrote upload endpoint to handle both `.sas` and `.zip`:
  - `.zip` files are extracted in-memory via `zipfile.ZipFile`
  - Each `.sas` file inside gets its own `file_id` and upload
  - Filters out `__MACOSX` entries
  - Added `application/zip` and `application/x-zip-compressed` to allowed MIME types
- **Files**: `backend/api/routes/conversions.py`

### Partitions ("No partition data available")
- Code plumbing verified correct: `file_id` stored on ConversionRow, endpoint queries `file_registry.db` by `source_file_id`
- Issue: partitions only appear after the full pipeline runs and PersistenceAgent writes to `file_registry.db`
- Old conversions created before the `file_id` column migration have no `file_id` → empty partitions expected
- New conversions will show partition data once the pipeline completes

### Layout Overflow Fix (from 31 May)
- Root cause was missing `min-w-0` on AdminLayout flex container and no `overflow-x-hidden` on `<main>`
- Fixed in both AdminLayout and UserLayout
- DiffView simplified: replaced per-line rendering with `<pre whitespace-pre-wrap break-words>`
- Report Card compacted: smaller cards, thinner bars, tighter spacing

---

## Session — Docker Hub Deployment + IP Protection

### Cython IP Protection (CDAIS + MIS)
- Created 3-stage Dockerfile: deps → Cython compilation → runtime
- Protected modules compiled to native `.so` binaries (practically impossible to reverse-engineer):
  - `partition/testing/cdais/cdais_runner.py`
  - `partition/testing/cdais/constraint_catalog.py`
  - `partition/testing/cdais/coverage_oracle.py`
  - `partition/testing/cdais/synthesizer.py`
  - `partition/invariant/invariant_synthesizer.py`
- Source `.py` files deleted from final image; only `.so` binaries remain
- **Files**: `infra/Dockerfile`, `infra/compile_protected.py`

### Docker Hub Push
- Building `tesnimeellabou/codara-backend:latest` and `tesnimeellabou/codara-frontend:latest`
- Backend: python:3.11-slim + all deps + Cython-compiled CDAIS/MIS
- Frontend: node:20-alpine build + nginx:alpine serve
- Fixed frontend Dockerfile: `npm install` → `npm ci` with `package-lock.json`

### Deployment Package (`deploy/`)
- `docker-compose.yml` — pulls from Docker Hub, wires redis + backend + frontend
- `nginx.conf` — proxy config for compose internal networking (http://backend:8000)
- `.env.example` — template with all required env vars documented
- Supervisor only needs: `docker compose up` after filling `.env`

---

## Session — Production Audit + Cleanup

### PySpark References Removed
- Removed PySpark from frontend dropdown (`dialogs.tsx`), pyproject.toml, project_config.yaml
- Removed `"spark"` from namespace_checker.py `_PRELOADED`
- Updated orchestrator docstring, architecture HTML docs
- Left planning/research docs untouched (historical)
- **Files**: `frontend/src/components/dialogs.tsx`, `pyproject.toml`, `backend/config/project_config.yaml`, `backend/partition/merge/namespace_checker.py`, `backend/partition/orchestration/orchestrator.py`, `docs/assets/architecture_v2.html`, `docs/assets/architecture_animated.html`

### CORS Already Configurable
- `settings.py` line 199-206 already reads `CORS_ORIGINS` env var (comma-separated) via pydantic-settings

### DuckDB Init Added to API Startup
- `init_all_duckdb_tables()` now called in `main.py` during startup, ensuring DuckDB tables exist before any pipeline run
- **Files**: `backend/api/main.py`

### Content-Disposition Filename Escaping
- All 4 download endpoints in conversions.py now quote filenames in Content-Disposition headers
- Prevents header injection with filenames containing spaces/special chars
- **Files**: `backend/api/routes/conversions.py`

### .env.example Created
- Root-level `.env.example` with all env vars documented (JWT, LLM providers, Redis, CORS, SMTP, etc.)
- Updated `deploy/.env.example` to match
- **Files**: `.env.example`, `deploy/.env.example`

### GitHub OAuth — No Action Needed
- Endpoint returns 501 when `GITHUB_CLIENT_ID`/`SECRET` are not set — clean graceful degradation

### Hardcoded Developer Paths Removed
- `test_streaming.py`: replaced `C:\Users\labou\Desktop\stagePfe\advanced_code.sas` with relative fixtures path
- `view_db_html.py`, `eval_cdais_direct.py`: replaced absolute paths in docstrings with generic `python scripts/...`
- **Files**: `backend/tests/test_streaming.py`, `backend/scripts/ops/view_db_html.py`, `backend/scripts/eval/eval_cdais_direct.py`

### Deploy Package Updated
- `nginx.conf`: added `client_max_body_size 50m`, `proxy_read_timeout 300s`, `proxy_connect_timeout 10s`
- **Files**: `deploy/nginx.conf`, `deploy/.env.example`

---

## Session 3 — Comprehensive Docker Testing & Bug Fixes

### KB Create FK Bug Fixed
- `POST /api/kb` returned 500 due to FK constraint failure: `KBChangelogRow.entry_id` referenced uncommitted `KBEntryRow.id`
- Fix: added `session.flush()` before `_log_change()` so the entry row is persisted before the changelog FK check
- **File**: `backend/api/routes/knowledge_base.py`

### Comprehensive Test Suite Created
- Created `infra/test_comprehensive.py` — 76 tests covering every API endpoint
- **File**: `infra/test_comprehensive.py`

### Test Results: 75 PASSED, 0 FAILED, 1 SKIPPED

| Section | Tests | Result |
|---------|-------|--------|
| 1. Health & Startup | 8 | ALL PASS |
| 2. Authentication | 13 | ALL PASS (signup, login, /me, logout, invalid tokens, duplicate registration) |
| 3. Knowledge Base API | 6 | ALL PASS (list, create, read, update, changelog) |
| 4. Conversions API | 7 | ALL PASS (upload, start, poll, partitions, code) |
| 5. Notifications | 2 | ALL PASS |
| 6. Analytics | 2 | ALL PASS |
| 7. User Settings | 2 | ALL PASS (preferences, profile) |
| 8. Projects | 4 | ALL PASS (list, create, conversions, update) |
| 9. Admin Access Control | 8 | ALL PASS (all 8 admin routes blocked for non-admin) |
| 10. Admin with Admin Token | 8 | ALL PASS (users, system-health, audit-logs, pipeline-config, prompts, cost, error-queue, file-registry) |
| 11. Edge Cases & Security | 8 | ALL PASS (404, SQL injection, XSS, long input, missing content-type, CORS) |
| 12. IP Protection (Cython) | 4 | ALL PASS (CDAIS .so present, .py removed; Invariant .so present, .py removed) |
| 13. Container Internals | 10 | ALL PASS (non-root user, PYTHONPATH, data dirs writable, no .env in image, HF cache) |

### IP Protection Verified
```
CDAIS .so files:
  cdais_runner.cpython-311-x86_64-linux-gnu.so          604 KB
  constraint_catalog.cpython-311-x86_64-linux-gnu.so   1147 KB
  coverage_oracle.cpython-311-x86_64-linux-gnu.so       818 KB
  synthesizer.cpython-311-x86_64-linux-gnu.so           937 KB
Invariant .so files:
  invariant_synthesizer.cpython-311-x86_64-linux-gnu.so 2721 KB
Source .py files: DELETED (only __init__.py remains)
```

### Docker Hub Images
- `tesnimeellabou/codara-backend:latest` — 5GB (includes Nomic model, CPU torch, all deps)
- `tesnimeellabou/codara-frontend:latest` — 94.5MB (nginx + built React app)

### Graceful Degradation Verified
- No Redis: `degraded` (checkpointing disabled, BackgroundTasks used)
- No Ollama/LLM: `unavailable` (conversion falls back to inline translation)
- No Azure services: all disabled gracefully (blob->local disk, queue->BackgroundTasks, telemetry->no-op)
- No Azure Key Vault: falls back to .env file
