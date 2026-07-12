"""商机 AI 下一步建议：阶段 + 最近 10 条跟进 + 停滞天数 + 画像摘要 → 3 条可执行动作。"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, get_llm_client
from app.ai.prompt_loader import render_prompt
from app.ai.schemas import NextActionOutput
from app.models.account import Account
from app.models.activity import Activity
from app.models.enums import ActivityRelatedType, ActivityType, LlmTaskType, OpportunityStage
from app.models.user import User
from app.services.lead_scoring import ACTIVITY_TYPE_LABELS
from app.services.opportunity_service import STAGE_LABELS, opportunity_service, stuck_days


def _profile_summary(ai_profile: dict[str, Any] | None) -> str | None:
    if not ai_profile:
        return None
    parts = []
    if overview := ai_profile.get("company_overview"):
        parts.append(str(overview))
    if pain_points := ai_profile.get("pain_points"):
        parts.append("痛点：" + "、".join(str(p) for p in pain_points))
    summary = " ".join(parts).strip()
    return summary[:300] or None


async def get_next_actions(
    session: AsyncSession,
    actor: User,
    opportunity_id: uuid.UUID,
    llm: LLMClient | None = None,
) -> NextActionOutput:
    opp = await opportunity_service.get(session, actor, opportunity_id)
    account = await session.scalar(select(Account).where(Account.id == opp.account_id))
    activities = list(
        await session.scalars(
            select(Activity)
            .where(
                Activity.related_type == ActivityRelatedType.OPPORTUNITY,
                Activity.related_id == opp.id,
                Activity.deleted_at.is_(None),
            )
            .order_by(Activity.created_at.desc())
            .limit(10)
        )
    )

    prompt = render_prompt(
        "next_action.j2",
        name=opp.name,
        account_name=account.name if account else "",
        stage_label=STAGE_LABELS[OpportunityStage(opp.stage)],
        stuck_days=stuck_days(opp),
        amount=f"{opp.amount:,.0f}",
        expected_close_date=(
            opp.expected_close_date.isoformat() if opp.expected_close_date else None
        ),
        profile_summary=_profile_summary(account.ai_profile if account else None),
        activities=[
            {
                "date": a.created_at.strftime("%Y-%m-%d"),
                "type_label": ACTIVITY_TYPE_LABELS.get(ActivityType(a.type), a.type),
                "content": a.content,
                "next_action": a.next_action,
            }
            for a in activities
        ],
    )
    llm = llm or get_llm_client()
    return await llm.chat_structured(
        LlmTaskType.NEXT_ACTION,
        [{"role": "user", "content": prompt}],
        NextActionOutput,
        user_id=actor.id,
    )
