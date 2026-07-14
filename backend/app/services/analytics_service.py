"""M12 业绩分析：月度指标聚合（本月 vs 上月）+ LLM 归因解读。

口径（PLAN §6.10）：
- 成交额/赢单数：stage_history 进入 won 的时间在当月
- 赢率：当月关闭（won+lost）中 won 占比；无关闭单时 win_rate=None
- 平均成交周期：当月赢单 created_at → won entered_at 天数均值
- 活动量：当月跟进记录数；新增线索：当月创建的线索数
"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, get_llm_client
from app.ai.prompt_loader import render_prompt
from app.ai.schemas import PerformanceInsightOutput
from app.core.timezone import BIZ_TZ, biz_today
from app.models.activity import Activity
from app.models.enums import LlmTaskType, OpportunityStage, Role
from app.models.lead import Lead
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.base import visibility_scope

ROLE_SCOPE_LABELS = {Role.SALES: "个人业绩", Role.MANAGER: "团队业绩", Role.ADMIN: "全公司业绩"}


def _month_bounds(month: date) -> tuple[datetime, datetime]:
    """业务时区（Asia/Shanghai）月界 → UTC。"""
    start = datetime(month.year, month.month, 1, tzinfo=BIZ_TZ)
    if month.month == 12:
        end = datetime(month.year + 1, 1, 1, tzinfo=BIZ_TZ)
    else:
        end = datetime(month.year, month.month + 1, 1, tzinfo=BIZ_TZ)
    return start.astimezone(UTC), end.astimezone(UTC)


def _prev_month(month: date) -> date:
    return date(month.year - 1, 12, 1) if month.month == 1 else date(month.year, month.month - 1, 1)


def _stage_entered_at(opp: Opportunity, stage: str) -> datetime | None:
    for item in reversed(opp.stage_history or []):
        if item.get("stage") == stage and item.get("entered_at"):
            dt = datetime.fromisoformat(item["entered_at"])
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return None


async def month_metrics(session: AsyncSession, actor: User, month: date) -> dict[str, Any]:
    """单月指标（按可见域）。closed = 当月进入 won/lost 的商机。"""
    start, end = _month_bounds(month)

    closed_stmt = visibility_scope(
        select(Opportunity).where(
            Opportunity.deleted_at.is_(None),
            Opportunity.stage.in_([OpportunityStage.WON.value, OpportunityStage.LOST.value]),
        ),
        Opportunity,
        actor,
    )
    closed = list(await session.scalars(closed_stmt))

    won_amount = Decimal(0)
    won_count = 0
    lost_count = 0
    cycle_days: list[int] = []
    for opp in closed:
        entered = _stage_entered_at(opp, opp.stage)
        if entered is None or not (start <= entered < end):
            continue
        if opp.stage == OpportunityStage.WON.value:
            won_count += 1
            won_amount += opp.amount
            created = (
                opp.created_at if opp.created_at.tzinfo else opp.created_at.replace(tzinfo=UTC)
            )
            cycle_days.append(max(0, (entered - created).days))
        else:
            lost_count += 1

    closed_count = won_count + lost_count
    win_rate = round(won_count / closed_count * 100, 1) if closed_count else None

    activity_stmt = (
        select(func.count())
        .select_from(Activity)
        .where(
            Activity.deleted_at.is_(None),
            Activity.created_at >= start,
            Activity.created_at < end,
        )
    )
    # count 语句的行类型是 tuple[int]，visibility_scope 泛型按模型标注——运行时行为一致
    activity_stmt = visibility_scope(activity_stmt, Activity, actor)  # type: ignore[misc]
    activity_count = int(await session.scalar(activity_stmt) or 0)

    leads_stmt = (
        select(func.count())
        .select_from(Lead)
        .where(
            Lead.deleted_at.is_(None),
            Lead.created_at >= start,
            Lead.created_at < end,
        )
    )
    leads_stmt = visibility_scope(leads_stmt, Lead, actor)  # type: ignore[misc]
    new_leads = int(await session.scalar(leads_stmt) or 0)

    return {
        "month": month.strftime("%Y-%m"),
        "won_amount": float(won_amount),
        "won_count": won_count,
        "lost_count": lost_count,
        "win_rate": win_rate,  # None = 当月无关闭商机
        "avg_cycle_days": round(sum(cycle_days) / len(cycle_days), 1) if cycle_days else None,
        "activity_count": activity_count,
        "new_leads": new_leads,
    }


async def performance_overview(
    session: AsyncSession, actor: User, month: date | None = None
) -> dict[str, Any]:
    month = (month or biz_today()).replace(day=1)
    prev = _prev_month(month)
    return {
        "scope": ROLE_SCOPE_LABELS.get(Role(actor.role), actor.role),
        "current": await month_metrics(session, actor, month),
        "previous": await month_metrics(session, actor, prev),
    }


async def generate_insight(
    session: AsyncSession, actor: User, month: date | None = None, llm: LLMClient | None = None
) -> PerformanceInsightOutput:
    llm = llm or get_llm_client()
    overview = await performance_overview(session, actor, month)
    prompt = render_prompt(
        "performance_insight.j2",
        scope_label=overview["scope"],
        month=overview["current"]["month"],
        prev_month=overview["previous"]["month"],
        current=json.dumps(overview["current"], ensure_ascii=False),
        previous=json.dumps(overview["previous"], ensure_ascii=False),
    )
    return await llm.chat_structured(
        LlmTaskType.PERFORMANCE_INSIGHT,
        [{"role": "user", "content": prompt}],
        PerformanceInsightOutput,
        user_id=actor.id,
    )
