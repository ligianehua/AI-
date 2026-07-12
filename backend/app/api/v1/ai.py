from typing import Annotated

from fastapi import APIRouter, Depends

from app.ai.client import LLMClient, get_llm_client
from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.models.enums import LlmTaskType
from app.schemas.ai import PingRequest, PingResponse
from app.schemas.script import FeedbackRequest
from app.services import llm_feedback

router = APIRouter(prefix="/ai", tags=["ai"])

LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]


@router.post("/feedback", status_code=204, summary="AI 生成结果反馈（1 赞 / -1 踩）")
async def set_feedback(
    body: FeedbackRequest, session: SessionDep, current_user: CurrentUserDep
) -> None:
    await llm_feedback.set_feedback(session, current_user, body.llm_call_id, body.feedback)


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
