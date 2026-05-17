"""Error Queue routes — failed conversions triage."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from api.core.auth import get_current_user
from api.core.database import ConversionRow, ConversionStageRow, UserRow, get_api_session
from api.core.schemas import ErrorQueueItemOut

router = APIRouter(prefix="/admin/error-queue", tags=["error-queue"])


def _require_admin(current_user: dict):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("", response_model=list[ErrorQueueItemOut])
def list_error_queue(current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    from api.main import engine

    session = get_api_session(engine)
    try:
        failed_convs = (
            session.query(ConversionRow)
            .filter(ConversionRow.status.in_(["failed", "partial"]))
            .order_by(ConversionRow.created_at.desc())
            .limit(50)
            .all()
        )

        results: list[ErrorQueueItemOut] = []
        for conv in failed_convs:
            failed_stage = (
                session.query(ConversionStageRow)
                .filter(
                    ConversionStageRow.conversion_id == conv.id,
                    ConversionStageRow.status == "failed",
                )
                .first()
            )

            stage_name = failed_stage.stage if failed_stage else "unknown"
            retries = failed_stage.retry_count if failed_stage else 0
            warnings = []
            if failed_stage and failed_stage.warnings:
                try:
                    warnings = json.loads(failed_stage.warnings)
                except (json.JSONDecodeError, TypeError):
                    pass

            error_msg = conv.validation_report or (warnings[0] if warnings else "Pipeline failure")
            if len(error_msg) > 200:
                error_msg = error_msg[:200] + "…"

            user = session.query(UserRow).filter(UserRow.id == conv.user_id).first()

            severity = "high" if conv.status == "failed" else "medium"
            if retries >= 3:
                severity = "high"

            model = "—"
            from api.core.database import AuditLogRow

            last_audit = (
                session.query(AuditLogRow)
                .filter(AuditLogRow.prompt_hash.contains(conv.id[:8]))
                .order_by(AuditLogRow.timestamp.desc())
                .first()
            )
            if last_audit:
                model = last_audit.model

            results.append(
                ErrorQueueItemOut(
                    id=conv.id,
                    fileName=conv.file_name,
                    stage=stage_name,
                    error=error_msg,
                    model=model,
                    retries=retries,
                    createdAt=conv.created_at,
                    severity=severity,
                    userId=conv.user_id,
                    userName=user.name if user else "Unknown",
                )
            )

        return results
    finally:
        session.close()


@router.post("/{conv_id}/retry")
def retry_conversion(conv_id: str, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    from api.main import engine

    session = get_api_session(engine)
    try:
        conv = session.query(ConversionRow).filter(ConversionRow.id == conv_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversion not found")
        if conv.status not in ("failed", "partial"):
            raise HTTPException(status_code=400, detail="Only failed/partial conversions can be retried")

        conv.status = "queued"
        session.query(ConversionStageRow).filter(
            ConversionStageRow.conversion_id == conv_id,
            ConversionStageRow.status == "failed",
        ).update({"status": "pending", "retry_count": ConversionStageRow.retry_count + 1})
        session.commit()
        return {"ok": True, "conversionId": conv_id}
    finally:
        session.close()


@router.delete("/{conv_id}")
def dismiss_error(conv_id: str, current_user: dict = Depends(get_current_user)):
    _require_admin(current_user)
    from api.main import engine

    session = get_api_session(engine)
    try:
        conv = session.query(ConversionRow).filter(ConversionRow.id == conv_id).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversion not found")
        session.delete(conv)
        session.commit()
        return {"ok": True}
    finally:
        session.close()
