"""仪表盘摘要测试：今日待办、本月成交额归月、漏斗、RBAC。"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Activity, Opportunity, User
from app.models.enums import ActivityRelatedType, ActivityType, OpportunityStage
from tests.conftest import RoleUsers

LoginFn = Callable[[str], Awaitable[dict[str, str]]]

NOW = datetime.now(UTC)


async def _seed_won_opp(
    session: AsyncSession, owner: User, amount: int, won_at: datetime
) -> Opportunity:
    account = Account(name=f"客户-{uuid.uuid4().hex[:6]}", owner_id=owner.id)
    session.add(account)
    await session.flush()
    opp = Opportunity(
        account_id=account.id,
        name=f"赢单-{uuid.uuid4().hex[:6]}",
        amount=Decimal(amount),
        stage=OpportunityStage.WON,
        probability=100,
        owner_id=owner.id,
        stage_history=[{"stage": "won", "entered_at": won_at.isoformat(), "by": "test"}],
    )
    session.add(opp)
    await session.commit()
    return opp


async def test_summary_won_month_todos_funnel(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    month_start = NOW.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # 本月赢单 30 万 + 上月赢单 99 万（不计入本月）
    await _seed_won_opp(session, roles.sales_a, 300_000, month_start + timedelta(hours=1))
    await _seed_won_opp(session, roles.sales_a, 990_000, month_start - timedelta(days=2))

    account = Account(name="待办客户", owner_id=roles.sales_a.id)
    session.add(account)
    await session.flush()
    today = NOW.date()
    session.add_all(
        [
            Activity(  # 逾期
                related_type=ActivityRelatedType.ACCOUNT,
                related_id=account.id,
                type=ActivityType.CALL,
                content="沟通",
                next_action="逾期的回访",
                next_action_date=today - timedelta(days=2),
                owner_id=roles.sales_a.id,
            ),
            Activity(  # 今日到期
                related_type=ActivityRelatedType.ACCOUNT,
                related_id=account.id,
                type=ActivityType.CALL,
                content="沟通",
                next_action="今天要发方案",
                next_action_date=today,
                owner_id=roles.sales_a.id,
            ),
            Activity(  # 未来，不出现
                related_type=ActivityRelatedType.ACCOUNT,
                related_id=account.id,
                type=ActivityType.CALL,
                content="沟通",
                next_action="下周的事",
                next_action_date=today + timedelta(days=7),
                owner_id=roles.sales_a.id,
            ),
            Activity(  # 别人的待办，不出现
                related_type=ActivityRelatedType.ACCOUNT,
                related_id=account.id,
                type=ActivityType.CALL,
                content="沟通",
                next_action="B 的待办",
                next_action_date=today,
                owner_id=roles.sales_b.id,
            ),
        ]
    )
    await session.commit()

    headers = await login("sales_a@test.cn")
    resp = await client.get("/api/v1/dashboard/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["won_amount_this_month"] == 300_000  # 上月的 99 万不计入

    todos = body["todos"]
    actions = [t["next_action"] for t in todos]
    assert actions == ["逾期的回访", "今天要发方案"]  # 按日期升序，未来与他人的不含
    assert todos[0]["overdue"] is True
    assert todos[1]["overdue"] is False
    assert todos[0]["related_label"] == "客户：待办客户"

    funnel = {f["stage"]: f["count"] for f in body["funnel"]}
    assert funnel["won"] == 2
    assert len(body["funnel"]) == 6  # 六阶段全出，含 0

    # manager 统计含团队，但待办只看本人
    resp = await client.get("/api/v1/dashboard/summary", headers=await login("manager_a@test.cn"))
    m = resp.json()
    assert m["won_amount_this_month"] == 300_000  # 团队可见
    assert m["todos"] == []  # 待办是个人的
