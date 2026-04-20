"""Codara API — FastAPI application entry point.

Startup order matters here:
  1. Load .env  →  2. Pull Key Vault secrets  →  3. Init settings
  4. Fail fast on weak JWT  →  5. Init telemetry  →  6. Start queue worker
  7. Init SQLite  →  8. Register routes  →  9. Seed default data

Telemetry must come before the DB so spans cover table creation time.
The queue worker must start before routes are registered so the first
incoming request can immediately enqueue a pipeline job.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# .env lives at the repo root, three levels up from backend/api/main.py
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

# Make sure `backend/` is importable as a package root — needed when running
# uvicorn from outside the backend/ directory (e.g. Docker, CI)
_pkg_root = str(Path(__file__).resolve().parent.parent)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings

# Catch weak JWT secrets before we accept a single request — better to crash
# at startup than to sign tokens with a known default and silently expose the app
settings.validate_production_secrets()

from api.core.database import get_api_engine, init_api_db, get_api_session, UserRow, KBEntryRow
from api.core.auth import hash_password
from api.middleware.logging_middleware import LoggingMiddleware
from api.middleware.error_handler import register_error_handlers

from api.routes import auth, conversions, knowledge_base, admin, analytics, settings as settings_route, notifications

# Telemetry spans must wrap everything that follows, so we init first.
# When APPLICATIONINSIGHTS_CONNECTION_STRING is absent this is a no-op.
from partition.orchestration.telemetry import _init_once as _init_telemetry
_init_telemetry()

# Start the Azure Queue consumer thread if AZURE_QUEUE_NAME is configured.
# In local dev this thread simply never picks up jobs (the queue is empty)
# and BackgroundTasks handles pipeline execution instead.
from api.services.queue_service import queue_service
queue_service.start_worker()

# ── Database ──────────────────────────────────────────────────────────────────

engine = get_api_engine(settings.sqlite_path)
init_api_db(engine)

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="Codara API", version=settings.app_version, description="SAS→Python conversion accelerator")

_log = structlog.get_logger("codara.api")

app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(auth.router,                prefix="/api")
app.include_router(conversions.router,         prefix="/api")
app.include_router(knowledge_base.router,      prefix="/api")
app.include_router(admin.router,               prefix="/api")
app.include_router(analytics.router,           prefix="/api")
app.include_router(settings_route.router,      prefix="/api")
app.include_router(notifications.router,       prefix="/api")


# ── Seed data ─────────────────────────────────────────────────────────────────

def _seed():
    """Populate the database with a default admin, a demo user, and a handful
    of KB entries the first time the app boots on a fresh database.

    Passwords are never hardcoded — they come from CODARA_ADMIN_PASSWORD /
    CODARA_USER_PASSWORD env vars, or get randomly generated and printed to
    stdout once so the operator can note them down.
    """
    import os
    import secrets
    from datetime import datetime, timezone

    session = get_api_session(engine)
    try:
        if session.query(UserRow).count() > 0:
            return  # already seeded on a previous boot — nothing to do

        now = datetime.now(timezone.utc).isoformat()

        def _get_or_generate_password(env_var: str, label: str) -> str:
            pw = os.environ.get(env_var)
            if pw:
                return pw
            # Generate a random password, log it to stdout (not the structured log
            # — we don't want it accidentally shipped to a logging service)
            pw = secrets.token_urlsafe(18)  # ~24 printable chars
            _log.warning(
                "generated_first_boot_password",
                account=label,
                env_var=env_var,
            )
            print(  # noqa: T201
                f"\n[Codara] First-boot password for {label}: {pw}"
                f"\n  Set {env_var}=<password> to pin this for future runs.\n"
            )
            return pw

        admin_pw = _get_or_generate_password("CODARA_ADMIN_PASSWORD", "admin@codara.dev")
        user_pw  = _get_or_generate_password("CODARA_USER_PASSWORD",  "user@codara.dev")

        session.add(UserRow(
            id="u-001",
            email="admin@codara.dev",
            name="Admin",
            hashed_password=hash_password(admin_pw),
            role="admin",
            status="active",
            email_verified=True,
            created_at=now,
        ))

        session.add(UserRow(
            id="u-002",
            email="user@codara.dev",
            name="Demo User",
            hashed_password=hash_password(user_pw),
            role="user",
            status="active",
            email_verified=True,
            created_at=now,
        ))

        # A few representative KB entries so the UI doesn't open to an empty
        # knowledge base on a fresh install
        kb_seeds = [
            ("kb-001", "proc sort data=mydata; by var1 var2; run;",
             "mydata = mydata.sort_values(['var1', 'var2'])", "data_manipulation", 0.98),
            ("kb-002", "proc means data=mydata mean std; var income; run;",
             "mydata['income'].agg(['mean', 'std'])", "statistics", 0.95),
            ("kb-003", "proc freq data=mydata; tables var1*var2 / chisq; run;",
             "pd.crosstab(mydata['var1'], mydata['var2'])\nfrom scipy.stats import chi2_contingency",
             "statistics", 0.89),
            ("kb-004", "data out; merge a(in=ina) b(in=inb); by id; if ina and inb; run;",
             "out = pd.merge(a, b, on='id', how='inner')", "data_manipulation", 0.97),
            ("kb-005", "%let threshold = 0.05;",
             "threshold = 0.05", "macro", 0.99),
            ("kb-006", "proc transpose data=long out=wide; by group; id time; var value; run;",
             "wide = long.pivot(index='group', columns='time', values='value')",
             "data_manipulation", 0.93),
        ]
        for kid, sas, py, cat, conf in kb_seeds:
            session.add(KBEntryRow(
                id=kid, sas_snippet=sas, python_translation=py,
                category=cat, confidence=conf, created_at=now, updated_at=now,
            ))

        session.commit()
    finally:
        session.close()


try:
    _seed()
except Exception as exc:
    _log.warning("seed_failed", error=str(exc))


# ── Health endpoint ───────────────────────────────────────────────────────────
# Used as the Azure Container Apps liveness / readiness probe.
# Each dependency is checked independently with a 2-second timeout so a
# slow Redis doesn't block the SQLite check (and vice versa).
# The endpoint always returns 200 — the "status" field in the body tells
# Azure whether to route traffic here.

@app.get("/api/health")
async def health():
    import asyncio

    async def _check_sqlite() -> str:
        try:
            from sqlalchemy import text
            from config.constants import HEALTH_CHECK_TIMEOUT_S

            async def _do():
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))

            await asyncio.wait_for(_do(), timeout=HEALTH_CHECK_TIMEOUT_S)
            return "ok"
        except Exception as exc:
            _log.warning("health_sqlite_fail", error=str(exc))
            return "unavailable"

    async def _check_redis() -> str:
        try:
            import redis as _redis
            from config.constants import HEALTH_CHECK_TIMEOUT_S

            async def _do():
                r = _redis.from_url(settings.redis_url)
                r.ping()

            await asyncio.wait_for(_do(), timeout=HEALTH_CHECK_TIMEOUT_S)
            return "ok"
        except Exception:
            # Redis is optional (checkpointing degrades) — report degraded, not down
            return "degraded"

    async def _check_lancedb() -> str:
        try:
            import lancedb
            from config.constants import HEALTH_CHECK_TIMEOUT_S

            async def _do():
                lancedb.connect(settings.lancedb_path)

            await asyncio.wait_for(_do(), timeout=HEALTH_CHECK_TIMEOUT_S)
            return "ok"
        except Exception:
            return "degraded"

    async def _check_ollama() -> str:
        try:
            import httpx
            from config.constants import HEALTH_CHECK_TIMEOUT_S, HEALTH_OLLAMA_HTTP_TIMEOUT_S

            async def _do():
                base = settings.ollama_base_url.replace("/v1", "")
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{base}/api/tags", timeout=HEALTH_OLLAMA_HTTP_TIMEOUT_S)
                    if resp.status_code == 200:
                        return "ok"
                return "unavailable"

            return await asyncio.wait_for(_do(), timeout=HEALTH_CHECK_TIMEOUT_S)
        except Exception:
            return "unavailable"

    sqlite_status, redis_status, lancedb_status, ollama_status = await asyncio.gather(
        _check_sqlite(),
        _check_redis(),
        _check_lancedb(),
        _check_ollama(),
    )

    # SQLite must be ok; Redis and LanceDB can be degraded without blocking traffic
    all_ok = all(
        s in ("ok", "degraded")
        for s in [sqlite_status, redis_status, lancedb_status]
    )

    return {
        "status": "ok" if all_ok else "degraded",
        "version": settings.app_version,
        "env": settings.app_env,
        "dependencies": {
            "sqlite": sqlite_status,
            "redis": redis_status,
            "lancedb": lancedb_status,
            "ollama": ollama_status,
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
