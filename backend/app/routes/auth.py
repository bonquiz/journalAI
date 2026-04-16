"""Login / logout routes. Cookie is Secure-flag dynamic: on localhost, secure=False
so the app works without HTTPS in dev; otherwise secure=True."""
from fastapi import APIRouter, HTTPException, Request, Response

from app.auth.password import verify_password
from app.auth.sessions import create_session, invalidate_session
from app.auth.totp import verify_code
from app.config import settings as env
from app.db import SessionLocal
from app.models.settings import AppSettings
from app.schemas.auth import LoginRequest

router = APIRouter(prefix="/api/auth")


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> dict:
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        if s is None or not verify_password(body.password, s.password_hash):
            raise HTTPException(401, "invalid credentials")
        if s.totp_secret:
            if not body.totp or not verify_code(s.totp_secret, body.totp):
                raise HTTPException(401, "invalid totp")

    sid = create_session()
    is_secure = env.domain != "localhost"
    response.set_cookie(
        "session", sid,
        httponly=True, secure=is_secure,
        samesite="strict", max_age=60 * 60 * env.session_absolute_hours, path="/",
    )
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    sid = getattr(request.state, "session_id", None)
    if sid:
        invalidate_session(sid)
    response.delete_cookie("session", path="/")
    return {"ok": True}
