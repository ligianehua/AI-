"""风险扫描单测：时间注入（mock now）验证三种风险 + 去重 + 已关闭商机不扫。"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Activity, Notification, Opportunity, User
from app.models.enums import (
    ActivityRelatedType,
    ActivityType,
    NotificationType,
    OpportunityStage,
)
from app.services.risk_service import scan_risks
from tests.conftest import RoleUsers

NOW = datetime(2026, 7, 12, 8, 0, tzinfo=UTC)  # 固定"当前时间"


async def _seed_opp(
    session: AsyncSession,
    owner: User,
    *,
    stage: OpportunityStage = OpportunityStage.PROPOSAL,
    stage_entered: datetime | None = None,
    name: str | None = None,
) -> Opportunity:
    account = Account(name=f"客户-{uuid.uuid4().hex[:6]}", owner_id=owner.id)
    session.add(account)
    await session.flush()
    opp = Opportunity(
        account_id=account.id,
        name=name or f"商机-{uuid.uuid4().hex[:6]}",
        amount=Decimal(100_000),
        stage=stage,
        probability=50,
        owner_id=owner.id,
        stage_history=(
            [{"stage": stage.value, "entered_at": stage_entered.isoformat(), "by": "test"}]
            if stage_entered
            else []
        ),
    )
    session.add(opp)
    await session.commit()
    return opp


async def _add_activity(
    session: AsyncSession,
    owner: User,
    opp: Opportunity,
    created_at: datetime,
    *,
    next_action: str | None = None,
    next_action_date: datetime | None = None,
) -> Activity:
    activity = Activity(
        related_type=ActivityRelatedType.OPPORTUNITY,
        related_id=opp.id,
        type=ActivityType.CALL,
        content="跟进内容",
        next_action=next_action,
        next_action_date=next_action_date.date() if next_action_date else None,
        owner_id=owner.id,
    )
    session.add(activity)
    await session.flush()
    activity.created_at = created_at  # 覆盖 server_default
    await session.commit()
    return activity


async def _notifications(session: AsyncSession, ntype: NotificationType) -> list[Notification]:
    return list(await session.scalars(select(Notification).where(Notification.type == ntype)))


async def test_stale_no_followup_detected(session: AsyncSession, roles: RoleUsers) -> None:
    opp = await _seed_opp(session, roles.sales_a, stage_entered=NOW - timedelta(days=2))
    await _add_activity(session, roles.sales_a, opp, NOW - timedelta(days=8))

    created = await scan_risks(session, now=NOW)
    assert created == 1
    rows = await _notifications(session, NotificationType.STALE_NO_FOLLOWUP)
    assert len(rows) == 1
    assert rows[0].user_id == roles.sales_a.id
    assert "8 天无跟进" in rows[0].title
    assert rows[0].related_id == opp.id


async def test_recent_followup_not_flagged(session: AsyncSession, roles: RoleUsers) -> None:
    opp = await _seed_opp(session, roles.sales_a, stage_entered=NOW - timedelta(days=2))
    await _add_activity(session, roles.sales_a, opp, NOW - timedelta(days=3))

    created = await scan_risks(session, now=NOW)
    assert created == 0


async def test_stage_stuck_detected(session: AsyncSession, roles: RoleUsers) -> None:
    opp = await _seed_opp(
        session, roles.sales_a, stage_entered=NOW - timedelta(days=25), name="停滞商机"
    )
    await _add_activity(session, roles.sales_a, opp, NOW - timedelta(days=1))  # 最近有跟进

    created = await scan_risks(session, now=NOW)
    assert created == 1
    rows = await _notifications(session, NotificationType.STAGE_STUCK)
    assert len(rows) == 1
    assert "停滞 25 天" in rows[0].title


async def test_won_lost_not_scanned(session: AsyncSession, roles: RoleUsers) -> None:
    await _seed_opp(
        session,
        roles.sales_a,
        stage=OpportunityStage.WON,
        stage_entered=NOW - timedelta(days=100),
    )
    await _seed_opp(
        session,
        roles.sales_a,
        stage=OpportunityStage.LOST,
        stage_entered=NOW - timedelta(days=100),
    )
    created = await scan_risks(session, now=NOW)
    assert created == 0


async def test_next_action_due_detected(session: AsyncSession, roles: RoleUsers) -> None:
    opp = await _seed_opp(session, roles.sales_a, stage_entered=NOW - timedelta(days=1))
    await _add_activity(
        session,
        roles.sales_a,
        opp,
        NOW - timedelta(days=2),
        next_action="给客户回电确认合同条款",
        next_action_date=NOW - timedelta(days=1),
    )
    created = await scan_risks(session, now=NOW)
    rows = await _notifications(session, NotificationType.NEXT_ACTION_DUE)
    assert len(rows) == 1
    assert "给客户回电确认合同条款" in rows[0].title
    assert created == 1


async def test_dedupe_unread_notifications(session: AsyncSession, roles: RoleUsers) -> None:
    """同一风险未读时重复扫描不再新增。"""
    opp = await _seed_opp(session, roles.sales_a, stage_entered=NOW - timedelta(days=30))
    await _add_activity(session, roles.sales_a, opp, NOW - timedelta(days=10))

    first = await scan_risks(session, now=NOW)
    assert first == 2  # stale + stuck
    second = await scan_risks(session, now=NOW)
    assert second == 0  # 未读去重


async def test_next_action_due_dedupe(session: AsyncSession, roles: RoleUsers) -> None:
    """到期提醒的去重键与写入键必须一致（回归：曾因键不一致导致每日重复轰炸）。"""
    opp = await _seed_opp(session, roles.sales_a, stage_entered=NOW - timedelta(days=1))
    await _add_activity(
        session,
        roles.sales_a,
        opp,
        NOW - timedelta(days=2),
        next_action="回访确认",
        next_action_date=NOW - timedelta(days=1),
    )
    first = await scan_risks(session, now=NOW)
    assert first == 1
    second = await scan_risks(session, now=NOW)
    assert second == 0
    rows = await _notifications(session, NotificationType.NEXT_ACTION_DUE)
    assert len(rows) == 1
