"""Login / logout routes. Cookie is Secure-flag dynamic: on localhost, secure=False
so the app works without HTTPS in dev; otherwise secure=True."""
import base64
from io import BytesIO

import qrcode
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.auth.password import verify_password
from app.auth.sessions import create_session, invalidate_all, invalidate_session
from app.auth.totp import generate_secret, provisioning_uri, verify_code
from app.config import settings as env
from app.db import SessionLocal
from app.models.settings import AppSettings
from app.schemas.auth import LoginRequest
from app.security.rate_limit import limiter

router = APIRouter(prefix="/api/auth")


@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest, response: Response) -> dict:
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


class TotpConfirm(BaseModel):
    code: str   # secret is read server-side from pending field


@router.post("/totp/setup")
async def totp_setup() -> dict:
    secret = generate_secret()
    uri = provisioning_uri(secret)
    img = qrcode.make(uri)
    buf = BytesIO()
    img.save(buf, format="PNG")
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        s.totp_pending_secret = secret
        db.commit()
    return {
        "secret": secret,
        "provisioning_uri": uri,
        "qr_png_base64": base64.b64encode(buf.getvalue()).decode(),
    }


@router.post("/totp/confirm")
async def totp_confirm(body: TotpConfirm, request: Request) -> dict:
    with SessionLocal() as db:
        s = db.get(AppSettings, 1)
        if not s.totp_pending_secret:
            raise HTTPException(400, "no pending TOTP setup — call /totp/setup first")
        if not verify_code(s.totp_pending_secret, body.code):
            raise HTTPException(400, "invalid code")
        s.totp_secret = s.totp_pending_secret
        s.totp_pending_secret = None
        db.commit()
    # Spec §5.2: invalidate all sessions after TOTP activation.
    invalidate_all()
    return {"ok": True, "note": "TOTP activated; please log in again"}
