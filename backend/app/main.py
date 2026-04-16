"""FastAPI application entrypoint.

Middleware is added bottom-up by Starlette, so the LAST added runs FIRST.
Current order (first to run at request time): SessionAuthMiddleware.
Future tasks will add CsrfMiddleware, SlowAPIMiddleware — order matters.
"""
from fastapi import FastAPI

from app.auth.middleware import SessionAuthMiddleware
from app.bootstrap import ensure_bootstrap
from app.routes.auth import router as auth_router

app = FastAPI(title="journalAI", docs_url=None, redoc_url=None)
app.add_middleware(SessionAuthMiddleware)


@app.on_event("startup")
async def _startup() -> None:
    ensure_bootstrap()

app.include_router(auth_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
