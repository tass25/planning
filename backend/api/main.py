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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.database import get_api_engine, init_api_db, get_api_session, UserRow, KBEntryRow
from api.auth import hash_password

from api.routes import auth, conversions, knowledge_base, admin, analytics, settings, notifications

# ── Database ──────────────────────────────────────────────────────────────────

DB_PATH = str(Path(__file__).resolve().parent.parent / "codara_api.db")
engine = get_api_engine(DB_PATH)
init_api_db(engine)

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="Codara API", version="3.0.0", description="SAS→Python conversion accelerator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://localhost:5173", "http://127.0.0.1:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include routers ──────────────────────────────────────────────────────────

app.include_router(auth.router,           prefix="/api")
app.include_router(conversions.router,    prefix="/api")
app.include_router(knowledge_base.router, prefix="/api")
app.include_router(admin.router,          prefix="/api")
app.include_router(analytics.router,      prefix="/api")
app.include_router(settings.router,       prefix="/api")
app.include_router(notifications.router,  prefix="/api")


# ── Seed data ─────────────────────────────────────────────────────────────────

def _seed():
    """Create default admin + demo user + seed KB entries if DB is empty."""
    from datetime import datetime, timezone
    session = get_api_session(engine)
    try:
        if session.query(UserRow).count() > 0:
            return  # already seeded

        now = datetime.now(timezone.utc).isoformat()

        # Admin user
        session.add(UserRow(
            id="u-001",
            email="admin@codara.dev",
            name="Admin",
            hashed_password=hash_password("admin123!"),
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
            hashed_password=hash_password("user123!"),
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


_seed()


# ── Health endpoint ───────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "3.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
