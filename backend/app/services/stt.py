"""Speech-to-text service using the OpenAI-compatible audio/transcriptions API.

Accepts raw bytes + filename and returns the transcript string. The caller is
responsible for discarding the audio bytes (the route handler does not persist).
"""
from app.services.llm_client import get_client


def transcribe(audio_bytes: bytes, filename: str) -> str:
    client, model = get_client("stt")
    # OpenAI SDK accepts a (filename, bytes) tuple for the file parameter.
    resp = client.audio.transcriptions.create(
        file=(filename, audio_bytes),
        model=model,
    )
    return resp.text
