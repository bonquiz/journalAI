"""FastAPI application entrypoint.

Middleware is added bottom-up by Starlette, so the LAST added runs FIRST.
Current order (first to run at request time): SlowAPIMiddleware, CsrfMiddleware, then SessionAuthMiddleware.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.auth.middleware import SessionAuthMiddleware
from app.bootstrap import ensure_bootstrap
from app.routes.auth import router as auth_router
from app.routes.chat import router as chat_router
from app.routes.entries import router as entries_router
from app.routes.health import router as health_router
from app.routes.search import router as search_router
from app.routes.settings import router as settings_router
from app.routes.tags import router as tags_router
from app.routes.transcribe import router as transcribe_router
from app.routes.tts import router as tts_router
from app.security.csrf import CsrfMiddleware
from app.security.rate_limit import limiter


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Startup
    ensure_bootstrap()
    from app.services.embedding_jobs import request_backfill, start_worker, stop_worker
    start_worker()
    request_backfill()  # kick off initial pass
    try:
        yield
    finally:
        await stop_worker()


app = FastAPI(title="journalAI", docs_url=None, redoc_url=None, lifespan=lifespan)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SessionAuthMiddleware)
app.add_middleware(CsrfMiddleware)


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request, exc):  # noqa: ANN001
    return JSONResponse({"detail": "rate_limited"}, status_code=429)


app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(entries_router)
app.include_router(health_router)
app.include_router(tags_router)
app.include_router(search_router)
app.include_router(settings_router)
app.include_router(transcribe_router)
app.include_router(tts_router)
