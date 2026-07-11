"""客户 AI 画像生成。

输入 = account 字段 + contacts + 全部跟进记录（时间线聚合口径）。
反幻觉：prompt 铁律写死"信息不足就说不足"；跟进 < 3 条时要求明确提示可靠性有限（eval 验证）。
LLM 失败时保留旧画像不覆盖。
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, get_llm_client
from app.ai.prompt_loader import render_prompt
from app.ai.schemas import AccountProfileOutput
from app.models.enums import ActivityType, ContactRoleInDeal, LlmTaskType
from app.models.user import User
from app.services.account_service import get_account_with_contacts, get_timeline
from app.services.lead_scoring import ACTIVITY_TYPE_LABELS

logger = logging.getLogger(__name__)

ROLE_IN_DEAL_LABELS = {
    ContactRoleInDeal.DECISION_MAKER: "决策人",
    ContactRoleInDeal.INFLUENCER: "影响者",
    ContactRoleInDeal.USER: "使用者",
    ContactRoleInDeal.GATEKEEPER: "守门人",
}


async def generate_profile(
    session: AsyncSession, actor: User, account_id: uuid.UUID, llm: LLMClient | None = None
) -> AccountProfileOutput:
    """生成画像并落库（同步执行体，由异步任务调用）。"""
    account, _, contacts = await get_account_with_contacts(session, actor, account_id)
    timeline = await get_timeline(session, actor, account_id)

    prompt = render_prompt(
        "account_profile.j2",
        name=account.name,
        industry=account.industry,
        size=account.size,
        region=account.region,
        remark=account.remark,
        activity_count=len(timeline),
        contacts=[
            {
                "name": c.name,
                "title": c.title,
                "role_label": (
                    ROLE_IN_DEAL_LABELS.get(ContactRoleInDeal(c.role_in_deal))
                    if c.role_in_deal
                    else None
                ),
                "remark": c.remark,
            }
            for c in contacts
        ],
        activities=[
            {
                "date": item.created_at.strftime("%Y-%m-%d"),
                "source_label": item.related_label,
                "type_label": ACTIVITY_TYPE_LABELS.get(ActivityType(item.type), item.type),
                "content": item.content,
                "next_action": item.next_action,
            }
            for item in timeline
        ],
    )

    llm = llm or get_llm_client()
    profile = await llm.chat_structured(
        LlmTaskType.ACCOUNT_PROFILE,
        [{"role": "user", "content": prompt}],
        AccountProfileOutput,
        user_id=account.owner_id,
    )

    account.ai_profile = profile.model_dump()
    account.ai_profile_updated_at = datetime.now(UTC)
    await session.commit()
    return profile
