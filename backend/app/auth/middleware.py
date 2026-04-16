"""Session-cookie authentication middleware.

OPEN_PATHS bypass auth entirely (e.g. /api/health, /api/auth/login).
Everything else under /api/* requires a valid session cookie.

On successful auth, the request proceeds, then touch_session() is invoked to
update last_activity_at (throttled to 1 write per 30s).
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.sessions import get_active_session, touch_session

OPEN_PATHS = {"/api/health", "/api/auth/login"}
# Note: /api/session/ping is NOT in OPEN_PATHS — it must go through auth so
# touch_session() fires as a deliberate heartbeat.


class SessionAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api"):
            return await call_next(request)
        if path in OPEN_PATHS:
            return await call_next(request)

        sid = request.cookies.get("session", "")
        sess = get_active_session(sid)
        if sess is None:
            return JSONResponse({"detail": "unauthorized"}, status_code=401)

        request.state.session_id = sid
        response = await call_next(request)
        touch_session(sid)
        return response
