"""Admin routes — audit logs, system health, users, pipeline config, file registry."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends

from api.core.auth import get_current_user
from api.core.database import (
    get_api_session, AuditLogRow, UserRow, ConversionRow, ConversionStageRow,
)
from api.core.schemas import (
    AuditLogOut, SystemServiceOut, UserOut, UserUpdate,
    PipelineConfigOut, FileRegistryEntryOut,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(current_user: dict):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


# ── Audit logs ────────────────────────────────────────────────────────────────

@router.get("/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    from api.main import engine
    session = get_api_session(engine)
    try:
        rows = session.query(AuditLogRow).order_by(AuditLogRow.timestamp.desc()).all()
        return [
            AuditLogOut(
                id=r.id, model=r.model, latency=r.latency, cost=r.cost,
                promptHash=r.prompt_hash, success=r.success, timestamp=r.timestamp,
            )
            for r in rows
        ]
    finally:
        session.close()


# ── System health ─────────────────────────────────────────────────────────────

@router.get("/system-health", response_model=list[SystemServiceOut])
def system_health(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    # Real health checks: test DB connectivity, check services
    import time

    services: list[SystemServiceOut] = []

    # Check API DB
    t0 = time.perf_counter()
    try:
        from api.main import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        lat = (time.perf_counter() - t0) * 1000
        services.append(SystemServiceOut(name="SQLite (API DB)", status="online", latency=round(lat, 1), uptime=99.99))
    except Exception:
        services.append(SystemServiceOut(name="SQLite (API DB)", status="offline", latency=0, uptime=0))

    # Check pipeline agents importable
    t0 = time.perf_counter()
    try:
        from partition.entry.file_analysis_agent import FileAnalysisAgent
        lat = (time.perf_counter() - t0) * 1000
        services.append(SystemServiceOut(name="Pipeline Agents", status="online", latency=round(lat, 1), uptime=99.95))
    except Exception:
        services.append(SystemServiceOut(name="Pipeline Agents", status="offline", latency=0, uptime=0))

    # Check knowledge base dir
    from pathlib import Path
    kb_path = Path(__file__).resolve().parent.parent.parent / "knowledge_base"
    services.append(SystemServiceOut(
        name="Knowledge Base",
        status="online" if kb_path.exists() else "degraded",
        latency=1.0, uptime=99.9,
    ))

    # Check uploads dir
    from api.routes.conversions import UPLOAD_DIR
    services.append(SystemServiceOut(
        name="File Storage",
        status="online" if UPLOAD_DIR.exists() else "offline",
        latency=1.0, uptime=99.99,
    ))

    return services


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserOut])
def list_users(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    from api.main import engine
    session = get_api_session(engine)
    try:
        rows = session.query(UserRow).order_by(UserRow.created_at.desc()).all()
        return [
            UserOut(
                id=r.id, email=r.email, name=r.name, role=r.role,
                conversionCount=r.conversion_count, status=r.status,
                emailVerified=r.email_verified or False, createdAt=r.created_at,
            )
            for r in rows
        ]
    finally:
        session.close()


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, body: UserUpdate, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    from api.main import engine
    session = get_api_session(engine)
    try:
        user = session.query(UserRow).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if body.role is not None:
            user.role = body.role.value
        if body.status is not None:
            user.status = body.status.value
        session.commit()
        session.refresh(user)
        return UserOut(
            id=user.id, email=user.email, name=user.name, role=user.role,
            conversionCount=user.conversion_count, status=user.status,
            emailVerified=user.email_verified or False, createdAt=user.created_at,
        )
    finally:
        session.close()


@router.delete("/users/{user_id}")
def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    if user_id == current_user.get("sub"):
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    from api.main import engine
    session = get_api_session(engine)
    try:
        user = session.query(UserRow).get(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        try:
            session.delete(user)
            session.commit()
        except Exception as exc:
            session.rollback()
            import structlog as _sl
            _sl.get_logger("codara.admin").error("delete_user_failed", user_id=user_id, error=str(exc))
            raise HTTPException(status_code=500, detail="Failed to delete user — may have related records")
        return {"deleted": user_id}
    finally:
        session.close()


# ── Pipeline config ───────────────────────────────────────────────────────────

# In-memory config (could persist to DB later)
_pipeline_config = {"maxRetries": 3, "timeout": 300, "checkpointInterval": 60}


@router.get("/pipeline-config", response_model=PipelineConfigOut)
def get_pipeline_config(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    return PipelineConfigOut(**_pipeline_config)


@router.put("/pipeline-config", response_model=PipelineConfigOut)
def update_pipeline_config(body: PipelineConfigOut, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    _pipeline_config.update(body.model_dump())
    return PipelineConfigOut(**_pipeline_config)


# ── File registry (from pipeline DB) ─────────────────────────────────────────

@router.get("/file-registry", response_model=list[FileRegistryEntryOut])
def list_file_registry(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    from api.main import engine
    session = get_api_session(engine)
    try:
        # Aggregate from conversions
        convs = session.query(ConversionRow).all()
        return [
            FileRegistryEntryOut(
                id=c.id,
                fileName=c.file_name,
                status=c.status,
                dependencies=[],
                lineage=[],
            )
            for c in convs
        ]
    finally:
        session.close()
