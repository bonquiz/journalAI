"""CSRF protection via double-submit token.

After /api/auth/login succeeds, the server sets a non-HttpOnly `csrf` cookie
with a random value. The frontend reads this cookie and sends its value as
X-CSRF-Token header on all state-changing requests. The server checks that
cookie and header match (constant-time compare).

Exempt paths: /api/auth/login (sets the cookie), /api/health (no auth).
"""
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings as env

CSRF_EXEMPT = {"/api/auth/login", "/api/health"}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Non-API or non-write: nothing to check, just pass through.
        # Exempt paths: also pass through, but set the csrf cookie on login success.
        if not path.startswith("/api") or request.method not in WRITE_METHODS or path in CSRF_EXEMPT:
            response = await call_next(request)
            if path == "/api/auth/login" and response.status_code == 200:
                response.set_cookie(
                    "csrf",
                    secrets.token_urlsafe(32),
                    httponly=False,
                    secure=(env.domain != "localhost"),
                    samesite="strict",
                    path="/",
                )
            return response

        # Write method + /api/* + not exempt: require matching cookie & header.
        cookie = request.cookies.get("csrf", "")
        header = request.headers.get("x-csrf-token", "")
        if not cookie or not header or not secrets.compare_digest(cookie, header):
            return JSONResponse({"detail": "csrf"}, status_code=403)
        return await call_next(request)
