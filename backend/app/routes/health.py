import httpx
from fastapi import APIRouter

from app.services.llm_client import get_client

router = APIRouter(prefix="/api")


async def _reachable(url: str) -> bool:
    """Probe URL with HEAD on the base. Fallback: GET /models for OpenAI-compatible servers.
    Avoids false negatives on STT/TTS servers that don't expose /models."""
    base = url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.head(base)
            if r.status_code < 500:
                return True
            r = await c.get(base + "/models")
            return r.status_code < 500
    except Exception:
        return False


@router.get("/health")
async def health() -> dict:
    checks: dict[str, bool] = {}
    for cap in ("stt", "chat", "embed", "tts"):
        client, _ = get_client(cap)
        checks[cap] = await _reachable(str(client.base_url))
    return {"status": "ok", "endpoints": checks}


@router.post("/session/ping")
async def session_ping() -> dict:
    """Lightweight heartbeat. Goes through auth middleware so touch_session fires."""
    return {"ok": True}
