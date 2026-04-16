from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest
from app.security.rate_limit import limiter
from app.services.chat import stream_chat

router = APIRouter(prefix="/api")


@router.post("/chat")
@limiter.limit("60/minute")
async def chat(request: Request, body: ChatRequest) -> StreamingResponse:
    def iter_sse():
        for tok in stream_chat(
            [m.model_dump() for m in body.messages],
            body.system_prompt_override,
        ):
            yield f"data: {tok}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(iter_sse(), media_type="text/event-stream")
