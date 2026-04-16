import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.schemas.chat import ChatRequest, FinalizeRequest
from app.security.rate_limit import limiter
from app.services.chat import finalize, stream_chat

router = APIRouter(prefix="/api")


@router.post("/chat")
@limiter.limit("60/minute")
async def chat(request: Request, body: ChatRequest) -> StreamingResponse:
    def iter_sse():
        # JSON-encode each token so that newlines / carriage returns inside
        # the chunk don't break SSE framing (which uses \n\n as message delim).
        for tok in stream_chat(
            [m.model_dump() for m in body.messages],
            body.system_prompt_override,
        ):
            yield f"data: {json.dumps(tok)}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(iter_sse(), media_type="text/event-stream")


@router.post("/chat/finalize")
@limiter.limit("30/minute")
async def chat_finalize(request: Request, body: FinalizeRequest) -> dict:
    return finalize([m.model_dump() for m in body.messages])
