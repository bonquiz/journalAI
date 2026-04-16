import logging

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.schemas.tts import TtsRequest
from app.security.rate_limit import limiter
from app.services.tts import synthesize

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _map_provider_error(exc: Exception) -> HTTPException:
    """Map OpenAI SDK / httpx failures to a 502 with a human-readable detail.
    We deliberately avoid leaking upstream error bodies (may contain PII or keys).
    """
    msg = str(exc).lower()
    if isinstance(exc, httpx.ConnectError) or "connecterror" in msg or "connection" in msg:
        return HTTPException(502, "TTS-Server nicht erreichbar")
    if "401" in msg or "unauthorized" in msg or "authentication" in msg:
        return HTTPException(502, "TTS-Server: Auth-Fehler (401) — API-Key prüfen")
    if "404" in msg or "not found" in msg:
        return HTTPException(502, "TTS-Server: Modell/Endpoint nicht gefunden (404)")
    if "429" in msg:
        return HTTPException(502, "TTS-Anbieter hat rate-limited — kurz warten")
    return HTTPException(502, "Vorlesen fehlgeschlagen — TTS-Endpoint prüfen")


@router.post("/tts")
@limiter.limit("30/minute")
async def tts_endpoint(request: Request, body: TtsRequest) -> StreamingResponse:
    try:
        audio = synthesize(body.text, voice=body.voice, speed=body.speed)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("TTS synthesis failed: %s", exc)
        raise _map_provider_error(exc) from exc

    return StreamingResponse(
        iter([audio]),
        media_type="audio/mpeg",
        headers={"Content-Disposition": 'inline; filename="tts.mp3"'},
    )
