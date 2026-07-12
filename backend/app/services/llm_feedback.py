"""生成类任务的用户反馈（赞/踩）→ llm_calls.feedback。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.enums import Role
from app.models.llm_call import LlmCall
from app.models.user import User


async def set_feedback(
    session: AsyncSession, actor: User, llm_call_id: uuid.UUID, feedback: int
) -> None:
    call = await session.scalar(select(LlmCall).where(LlmCall.id == llm_call_id))
    if call is None or (actor.role != Role.ADMIN and call.user_id != actor.id):
        raise NotFoundError("调用记录不存在")
    call.feedback = feedback if feedback != 0 else None
    await session.commit()
