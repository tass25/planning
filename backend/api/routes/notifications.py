"""Notification routes — list, mark read, mark all read."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.core.auth import get_current_user
from api.core.database import NotificationRow, get_api_session
from api.core.schemas import NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _notif_to_out(row: NotificationRow) -> NotificationOut:
    return NotificationOut(
        id=row.id,
        userId=row.user_id,
        title=row.title,
        message=row.message,
        type=row.type,
        read=row.read,
        createdAt=row.created_at,
    )


@router.get("", response_model=list[NotificationOut])
def list_notifications(current_user: dict = Depends(get_current_user)):
    from api.main import engine

    session = get_api_session(engine)
    try:
        rows = (
            session.query(NotificationRow)
            .filter(NotificationRow.user_id == current_user["sub"])
            .order_by(NotificationRow.created_at.desc())
            .limit(50)
            .all()
        )
        return [_notif_to_out(r) for r in rows]
    finally:
        session.close()


@router.put("/{notif_id}/read")
def mark_read(notif_id: str, current_user: dict = Depends(get_current_user)):
    from api.main import engine

    session = get_api_session(engine)
    try:
        row = (
            session.query(NotificationRow)
            .filter(
                NotificationRow.id == notif_id,
                NotificationRow.user_id == current_user["sub"],
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Notification not found")
        row.read = True
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise HTTPException(status_code=500, detail="Failed to mark notification as read")
        return {"ok": True}
    finally:
        session.close()


@router.put("/read-all")
def mark_all_read(current_user: dict = Depends(get_current_user)):
    from api.main import engine

    session = get_api_session(engine)
    try:
        session.query(NotificationRow).filter(
            NotificationRow.user_id == current_user["sub"],
            NotificationRow.read.is_(False),
        ).update({"read": True})
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise HTTPException(status_code=500, detail="Failed to mark notifications as read")
        return {"ok": True}
    finally:
        session.close()
