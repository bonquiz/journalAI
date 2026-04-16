"""FastAPI application entrypoint.

Middleware is added bottom-up by Starlette, so the LAST added runs FIRST.
Current order (first to run at request time): SessionAuthMiddleware.
Future tasks will add CsrfMiddleware, SlowAPIMiddleware — order matters.
"""
from fastapi import FastAPI

from app.auth.middleware import SessionAuthMiddleware

app = FastAPI(title="journalAI", docs_url=None, redoc_url=None)
app.add_middleware(SessionAuthMiddleware)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
