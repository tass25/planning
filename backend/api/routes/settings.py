"""Settings routes — profile and preferences."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends

from api.auth import get_current_user, hash_password
from api.database import get_api_session, UserRow
from api.schemas import UserOut, ProfileUpdate, PreferencesUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


@router.put("/profile", response_model=UserOut)
def update_profile(body: ProfileUpdate, current_user: dict = Depends(get_current_user)):
    from api.main import engine
    session = get_api_session(engine)
    try:
        user = session.query(UserRow).get(current_user["sub"])
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if body.name is not None:
            user.name = body.name
        if body.email is not None:
            if body.email != user.email:
                existing = session.query(UserRow).filter(UserRow.email == body.email).first()
                if existing:
                    raise HTTPException(status_code=409, detail="Email already taken")
            user.email = body.email
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise HTTPException(status_code=500, detail="Failed to update profile")
        session.refresh(user)
        return UserOut(
            id=user.id, email=user.email, name=user.name, role=user.role,
            conversionCount=user.conversion_count, status=user.status,
            emailVerified=user.email_verified or False, createdAt=user.created_at,
        )
    finally:
        session.close()


@router.put("/preferences")
def update_preferences(body: PreferencesUpdate, current_user: dict = Depends(get_current_user)):
    from api.main import engine
    session = get_api_session(engine)
    try:
        user = session.query(UserRow).get(current_user["sub"])
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if body.defaultRuntime is not None:
            user.default_runtime = body.defaultRuntime.value
        if body.emailNotifications is not None:
            user.email_notifications = body.emailNotifications
        try:
            session.commit()
        except Exception as exc:
            session.rollback()
            raise HTTPException(status_code=500, detail="Failed to update preferences")
        return {"status": "ok"}
    finally:
        session.close()
