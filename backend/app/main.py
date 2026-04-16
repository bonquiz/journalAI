"""FastAPI application entrypoint.

Middleware is added bottom-up by Starlette, so the LAST added runs FIRST.
Current order (first to run at request time): SlowAPIMiddleware, CsrfMiddleware, then SessionAuthMiddleware.
"""
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.auth.middleware import SessionAuthMiddleware
from app.bootstrap import ensure_bootstrap
from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.entries import router as entries_router
from app.routes.health import router as health_router
from app.routes.tags import router as tags_router
from app.routes.settings import router as settings_router
from app.routes.transcribe import router as transcribe_router
from app.security.csrf import CsrfMiddleware
from app.security.rate_limit import limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

app = FastAPI(title="journalAI", docs_url=None, redoc_url=None)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SessionAuthMiddleware)
app.add_middleware(CsrfMiddleware)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request, exc):
    return JSONResponse({"detail": "rate_limited"}, status_code=429)


@app.on_event("startup")
async def _startup() -> None:
    ensure_bootstrap()

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(entries_router)
app.include_router(health_router)
app.include_router(tags_router)
app.include_router(settings_router)
app.include_router(transcribe_router)
