"""工作台摘要：统计按可见域聚合；今日待办只看本人（PLAN §6.5，纯聚合查询）。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.activity import Activity
from app.models.base import AppModel
from app.models.enums import ActivityRelatedType, OpportunityStage
from app.models.lead import Lead
from app.models.opportunity import Opportunity
from app.models.user import User
from app.schemas.dashboard import DashboardSummary, FunnelItem, TodoItem
from app.services.base import visibility_scope
from app.services.opportunity_service import stage_entered_at


async def _count[M: AppModel](session: AsyncSession, stmt: Select[tuple[M]]) -> int:
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    return int(total or 0)


async def _won_amount_this_month(session: AsyncSession, actor: User, now: datetime) -> float:
    """won 商机按进入赢单阶段的时间归月（stage_history 最后一条）。"""
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    won_stmt = visibility_scope(
        select(Opportunity).where(
            Opportunity.deleted_at.is_(None), Opportunity.stage == OpportunityStage.WON
        ),
        Opportunity,
        actor,
    )
    total = 0.0
    for opp in await session.scalars(won_stmt):
        if stage_entered_at(opp) >= month_start:
            total += float(opp.amount)
    return total


async def _todos(session: AsyncSession, actor: User, now: datetime) -> list[TodoItem]:
    """本人 next_action 已到期（含逾期 7 天内）的跟进计划，最多 10 条。"""
    today = now.date()
    rows = list(
        await session.scalars(
            select(Activity)
            .where(
                Activity.owner_id == actor.id,
                Activity.deleted_at.is_(None),
                Activity.next_action.is_not(None),
                Activity.next_action_date.is_not(None),
                Activity.next_action_date <= today,
            )
            .order_by(Activity.next_action_date.asc())
            .limit(10)
        )
    )
    # 批量取宿主实体名称
    ids_by_type: dict[ActivityRelatedType, list[uuid.UUID]] = {}
    for a in rows:
        ids_by_type.setdefault(ActivityRelatedType(a.related_type), []).append(a.related_id)
    labels: dict[uuid.UUID, str] = {}
    if lead_ids := ids_by_type.get(ActivityRelatedType.LEAD):
        for row in await session.execute(
            select(Lead.id, Lead.account_name).where(Lead.id.in_(lead_ids))
        ):
            labels[row[0]] = f"线索：{row[1]}"
    if account_ids := ids_by_type.get(ActivityRelatedType.ACCOUNT):
        for row in await session.execute(
            select(Account.id, Account.name).where(Account.id.in_(account_ids))
        ):
            labels[row[0]] = f"客户：{row[1]}"
    if opp_ids := ids_by_type.get(ActivityRelatedType.OPPORTUNITY):
        for row in await session.execute(
            select(Opportunity.id, Opportunity.name).where(Opportunity.id.in_(opp_ids))
        ):
            labels[row[0]] = f"商机：{row[1]}"

    return [
        TodoItem(
            activity_id=a.id,
            next_action=a.next_action or "",
            next_action_date=a.next_action_date,
            related_type=ActivityRelatedType(a.related_type),
            related_label=labels.get(a.related_id, ""),
            overdue=bool(a.next_action_date and a.next_action_date < today),
        )
        for a in rows
    ]


async def summary(session: AsyncSession, actor: User) -> DashboardSummary:
    now = datetime.now(UTC)
    leads = visibility_scope(select(Lead).where(Lead.deleted_at.is_(None)), Lead, actor)
    accounts = visibility_scope(select(Account).where(Account.deleted_at.is_(None)), Account, actor)
    opportunities = visibility_scope(
        select(Opportunity).where(Opportunity.deleted_at.is_(None)), Opportunity, actor
    )
    pipeline = visibility_scope(
        select(Opportunity).where(
            Opportunity.deleted_at.is_(None),
            Opportunity.stage.notin_([OpportunityStage.WON, OpportunityStage.LOST]),
        ),
        Opportunity,
        actor,
    ).subquery()
    pipeline_amount = await session.scalar(select(func.coalesce(func.sum(pipeline.c.amount), 0)))

    funnel_rows = (
        await session.execute(
            visibility_scope(
                select(Opportunity).where(Opportunity.deleted_at.is_(None)),
                Opportunity,
                actor,
            )
            .with_only_columns(Opportunity.stage, func.count())
            .group_by(Opportunity.stage)
        )
    ).all()
    counts = {row[0]: int(row[1]) for row in funnel_rows}
    funnel = [FunnelItem(stage=s, count=counts.get(s, 0)) for s in OpportunityStage]

    return DashboardSummary(
        lead_count=await _count(session, leads),
        account_count=await _count(session, accounts),
        opportunity_count=await _count(session, opportunities),
        pipeline_amount=float(pipeline_amount or 0),
        won_amount_this_month=await _won_amount_this_month(session, actor, now),
        funnel=funnel,
        todos=await _todos(session, actor, now),
    )
