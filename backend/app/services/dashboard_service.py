"""工作台摘要：按可见域聚合统计。"""

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.base import AppModel
from app.models.enums import OpportunityStage
from app.models.lead import Lead
from app.models.opportunity import Opportunity
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.services.base import visibility_scope


async def _count[M: AppModel](session: AsyncSession, stmt: Select[tuple[M]]) -> int:
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    return int(total or 0)


async def summary(session: AsyncSession, actor: User) -> DashboardSummary:
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

    return DashboardSummary(
        lead_count=await _count(session, leads),
        account_count=await _count(session, accounts),
        opportunity_count=await _count(session, opportunities),
        pipeline_amount=float(pipeline_amount or 0),
    )
