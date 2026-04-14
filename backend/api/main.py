"""Codara API — main FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root (Stage/.env — three levels up from backend/api/main.py)
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

# Ensure backend/ package is importable
_pkg_root = str(Path(__file__).resolve().parent.parent)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from api.core.database import get_api_engine, init_api_db, get_api_session, UserRow, KBEntryRow
from api.core.auth import hash_password
from api.middleware.logging_middleware import LoggingMiddleware
from api.middleware.error_handler import register_error_handlers

from api.routes import auth, conversions, knowledge_base, admin, analytics, settings as settings_route, notifications

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

# ── Global error handlers ─────────────────────────────────────────────────────
register_error_handlers(app)

# ── Include routers ──────────────────────────────────────────────────────────

app.include_router(auth.router,                prefix="/api")
app.include_router(conversions.router,         prefix="/api")
app.include_router(knowledge_base.router,      prefix="/api")
app.include_router(admin.router,               prefix="/api")
app.include_router(analytics.router,           prefix="/api")
app.include_router(settings_route.router,      prefix="/api")
app.include_router(notifications.router,       prefix="/api")


# ── Seed data ─────────────────────────────────────────────────────────────────

def _seed():
    """Create default admin + demo user + seed KB entries if DB is empty.

    Passwords are sourced from env vars CODARA_ADMIN_PASSWORD and
    CODARA_USER_PASSWORD.  If not set, a random 24-char password is
    generated and printed ONCE to stdout so the operator can note it.
    Hardcoded default passwords are intentionally NOT used.
    """
    import os
    import secrets
    from datetime import datetime, timezone

    session = get_api_session(engine)
    try:
        if session.query(UserRow).count() > 0:
            return  # already seeded

        now = datetime.now(timezone.utc).isoformat()

        def _get_or_generate_password(env_var: str, label: str) -> str:
            pw = os.environ.get(env_var)
            if pw:
                return pw
            pw = secrets.token_urlsafe(18)  # ~24 printable chars
            _log.warning(
                "generated_first_boot_password",
                account=label,
                env_var=env_var,
                password=pw,
            )
            print(  # noqa: T201 — deliberate first-boot output
                f"\n[Codara] First-boot password for {label}: {pw}"
                f"\n  Set {env_var}=<password> to pin this for future runs.\n"
            )
            return pw

        admin_pw = _get_or_generate_password("CODARA_ADMIN_PASSWORD", "admin@codara.dev")
        user_pw  = _get_or_generate_password("CODARA_USER_PASSWORD",  "user@codara.dev")

        # Admin user
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

        # Demo user
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

        # Seed KB entries (same as UI mock)
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
# Azure Container Apps liveness/readiness probe target.
# Each dependency check has a 2s timeout and never crashes the endpoint.

@app.get("/api/health")
async def health():
    import asyncio

    async def _check_sqlite() -> str:
        try:
            from sqlalchemy import text
            from config.constants import HEALTH_CHECK_TIMEOUT_S
            async with asyncio.timeout(HEALTH_CHECK_TIMEOUT_S):
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            return "ok"
        except Exception as exc:
            _log.warning("health_sqlite_fail", error=str(exc))
            return "unavailable"

    async def _check_redis() -> str:
        try:
            import redis as _redis
            from config.constants import HEALTH_CHECK_TIMEOUT_S
            async with asyncio.timeout(HEALTH_CHECK_TIMEOUT_S):
                r = _redis.from_url(settings.redis_url)
                r.ping()
            return "ok"
        except Exception:
            return "degraded"

    async def _check_lancedb() -> str:
        try:
            import lancedb
            from config.constants import HEALTH_CHECK_TIMEOUT_S
            async with asyncio.timeout(HEALTH_CHECK_TIMEOUT_S):
                lancedb.connect(settings.lancedb_path)
            return "ok"
        except Exception:
            return "degraded"

    async def _check_ollama() -> str:
        try:
            import httpx
            from config.constants import HEALTH_CHECK_TIMEOUT_S, HEALTH_OLLAMA_HTTP_TIMEOUT_S
            async with asyncio.timeout(HEALTH_CHECK_TIMEOUT_S):
                base = settings.ollama_base_url.replace("/v1", "")
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{base}/api/tags", timeout=HEALTH_OLLAMA_HTTP_TIMEOUT_S)
                    if resp.status_code == 200:
                        return "ok"
            return "unavailable"
        except Exception:
            return "unavailable"

    sqlite_status, redis_status, lancedb_status, ollama_status = await asyncio.gather(
        _check_sqlite(),
        _check_redis(),
        _check_lancedb(),
        _check_ollama(),
    )

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
