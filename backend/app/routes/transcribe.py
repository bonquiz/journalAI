from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.config import settings as env
from app.security.rate_limit import limiter
from app.services.stt import transcribe

router = APIRouter(prefix="/api")


@router.post("/transcribe")
@limiter.limit("20/minute")
async def transcribe_endpoint(
    request: Request, file: UploadFile = File(...)
) -> dict[str, str]:
    max_bytes = env.max_upload_mb * 1024 * 1024
    audio = await file.read()
    if len(audio) > max_bytes:
        raise HTTPException(413, "file too large")
    text = transcribe(audio, file.filename or "audio.webm")
    # Deliberately NOT persisted — privacy requirement (spec §8)
    return {"transcript": text}
