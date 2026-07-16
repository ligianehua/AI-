from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.ai.client import LLMClient, get_llm_client
from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.schemas.assistant import ChatRequest
from app.services import product_advisor_service

router = APIRouter(prefix="/product-advisor", tags=["product-advisor"])

LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]


@router.post("/chat", summary="产品咨询对话（售前专家/售后运维双角色，SSE）")
async def chat(
    body: ChatRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
    llm: LLMClientDep,
) -> StreamingResponse:
    return StreamingResponse(
        product_advisor_service.chat_stream_events(session, current_user, body, llm=llm),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
