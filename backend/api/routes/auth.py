"""Authentication routes — login, signup, me, logout, email verification, GitHub OAuth."""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import httpx
from config.settings import settings
from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.core.auth import create_access_token, get_current_user, hash_password, verify_password
from api.core.database import NotificationRow, UserRow, get_api_session
from api.core.schemas import (
    AuthResponse,
    GitHubCallbackRequest,
    LoginRequest,
    SignupRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

GITHUB_CLIENT_ID = settings.github_client_id
GITHUB_CLIENT_SECRET = settings.github_client_secret

# ── Simple in-memory rate limiter ────────────────────────────────────────────
# Tracks (ip, endpoint) → list of attempt timestamps within the window.
_RATE_LIMIT_WINDOW_S = 60
_RATE_LIMIT_MAX_ATTEMPTS = 5
_rate_lock = threading.Lock()
_rate_store: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(request: Request, endpoint: str) -> None:
    """Raise HTTP 429 if the caller exceeds MAX_ATTEMPTS per WINDOW_S."""
    ip = request.client.host if request.client else "unknown"
    key = f"{ip}:{endpoint}"
    now = time.monotonic()
    with _rate_lock:
        attempts = _rate_store[key]
        # Evict timestamps outside the current window
        _rate_store[key] = [t for t in attempts if now - t < _RATE_LIMIT_WINDOW_S]
        if len(_rate_store[key]) >= _RATE_LIMIT_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many attempts. Try again in {_RATE_LIMIT_WINDOW_S}s.",
            )
        _rate_store[key].append(now)


def _user_to_out(row: UserRow) -> UserOut:
    return UserOut(
        id=row.id,
        email=row.email,
        name=row.name,
        role=row.role,
        conversionCount=row.conversion_count,
        status=row.status,
        emailVerified=row.email_verified or False,
        createdAt=row.created_at,
    )


def _create_notification(session, user_id: str, title: str, message: str, ntype: str = "info"):
    session.add(
        NotificationRow(
            id=f"notif-{uuid.uuid4().hex[:8]}",
            user_id=user_id,
            title=title,
            message=message,
            type=ntype,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request):
    _check_rate_limit(request, "login")
    from api.main import engine

    session = get_api_session(engine)
    try:
        user = session.query(UserRow).filter(UserRow.email == body.email).first()
        if (
            not user
            or not user.hashed_password
            or not verify_password(body.password, user.hashed_password)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )
        if user.status == "suspended":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account suspended")
        token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
        return AuthResponse(user=_user_to_out(user), token=token)
    finally:
        session.close()


@router.post("/signup", response_model=AuthResponse)
def signup(body: SignupRequest, request: Request):
    _check_rate_limit(request, "signup")
    from api.main import engine

    session = get_api_session(engine)
    try:
        if session.query(UserRow).filter(UserRow.email == body.email).first():
            raise HTTPException(status_code=400, detail="Email already registered")

        verification_token = secrets.token_urlsafe(32)
        user = UserRow(
            id=f"u-{uuid.uuid4().hex[:8]}",
            email=body.email,
            name=body.name,
            hashed_password=hash_password(body.password),
            role="user",
            status="active",
            email_verified=False,
            verification_token=verification_token,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        session.add(user)
        session.flush()

        _create_notification(
            session,
            user.id,
            "Welcome to Codara!",
            "Your account has been created. Please verify your email to unlock all features.",
            "info",
        )
        _create_notification(
            session,
            user.id,
            "Email Verification Required",
            f"Use this verification token: {verification_token}",
            "warning",
        )

        session.commit()
        session.refresh(user)
        token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
        return AuthResponse(
            user=_user_to_out(user),
            token=token,
            emailVerificationRequired=True,
        )
    finally:
        session.close()


@router.post("/verify-email")
def verify_email(token: str):
    from api.main import engine

    session = get_api_session(engine)
    try:
        user = session.query(UserRow).filter(UserRow.verification_token == token).first()
        if not user:
            raise HTTPException(status_code=400, detail="Invalid verification token")
        user.email_verified = True
        user.verification_token = None

        _create_notification(
            session,
            user.id,
            "Email Verified",
            "Your email has been verified successfully. All features are now unlocked.",
            "success",
        )

        session.commit()
        return {"message": "Email verified successfully"}
    finally:
        session.close()


@router.get("/github/url")
def github_login_url():
    """Return the GitHub OAuth authorization URL."""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=501,
            detail="GitHub OAuth not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET env vars.",
        )
    return {
        "url": f"https://github.com/login/oauth/authorize?client_id={GITHUB_CLIENT_ID}&scope=user:email"
    }


@router.post("/github/callback", response_model=AuthResponse)
async def github_callback(body: GitHubCallbackRequest):
    """Exchange GitHub code for user info and create/login user."""
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured")

    async with httpx.AsyncClient() as client:
        # Exchange code for access token
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            json={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": body.code,
            },
            headers={"Accept": "application/json"},
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="GitHub token exchange failed")

        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=400,
                detail=token_data.get("error_description", "Failed to get access token"),
            )

        # Get user info
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        if user_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch GitHub user info")
        try:
            gh_user = user_resp.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid response from GitHub user API")
        if not isinstance(gh_user, dict) or "id" not in gh_user:
            raise HTTPException(status_code=400, detail="GitHub user info missing required fields")

        # Get email
        email_resp = await client.get(
            "https://api.github.com/user/emails",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        try:
            emails = email_resp.json() if email_resp.status_code == 200 else []
        except Exception:
            emails = []
        if not isinstance(emails, list):
            emails = []
        primary_email = next(
            (
                e["email"]
                for e in emails
                if isinstance(e, dict) and e.get("primary") and e.get("email")
            ),
            None,
        )
        if not primary_email:
            primary_email = (
                gh_user.get("email") or f"{gh_user.get('login', 'unknown')}@github.local"
            )

    from api.main import engine

    session = get_api_session(engine)
    try:
        gh_id = str(gh_user.get("id", ""))
        user = session.query(UserRow).filter(UserRow.github_id == gh_id).first()

        if not user:
            # Check if email already exists (link accounts)
            user = session.query(UserRow).filter(UserRow.email == primary_email).first()
            if user:
                user.github_id = gh_id
                user.email_verified = True
            else:
                user = UserRow(
                    id=f"u-{uuid.uuid4().hex[:8]}",
                    email=primary_email,
                    name=gh_user.get("name") or gh_user.get("login", "github-user"),
                    hashed_password=None,
                    role="user",
                    status="active",
                    email_verified=True,
                    github_id=gh_id,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
                session.add(user)
                session.flush()

                _create_notification(
                    session,
                    user.id,
                    "Welcome to Codara!",
                    "Your account has been created via GitHub. Start converting SAS files now!",
                    "success",
                )

        session.commit()
        session.refresh(user)
        jwt_token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
        return AuthResponse(user=_user_to_out(user), token=jwt_token)
    finally:
        session.close()


@router.get("/me", response_model=UserOut)
def me(current_user: dict = Depends(get_current_user)):
    from api.main import engine

    session = get_api_session(engine)
    try:
        user = session.query(UserRow).filter(UserRow.id == current_user["sub"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return _user_to_out(user)
    finally:
        session.close()


@router.post("/logout")
def logout():
    return {"message": "Logged out"}
