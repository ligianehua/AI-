from typing import Annotated

from fastapi import APIRouter, Depends

from app.ai.client import LLMClient, get_llm_client
from app.core.deps import CurrentUserDep
from app.models.enums import LlmTaskType
from app.schemas.ai import PingRequest, PingResponse

router = APIRouter(prefix="/ai", tags=["ai"])

LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]


@router.post("/ping", summary="AI 冒烟：验证供应商连通与记账")
async def ping(body: PingRequest, current_user: CurrentUserDep, llm: LLMClientDep) -> PingResponse:
    result = await llm.chat(
        LlmTaskType.PING,
        [
            {"role": "system", "content": "你是连通性测试助手，请简短回复。"},
            {"role": "user", "content": body.message},
        ],
        user_id=current_user.id,
    )
    return PingResponse(
        reply=result.content,
        provider=result.provider,
        model=result.model,
        latency_ms=result.latency_ms,
    )
