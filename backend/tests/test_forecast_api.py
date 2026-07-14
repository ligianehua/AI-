"""M11 销售预测：加权口径、快照幂等、可见域聚合、外推数据量守卫。"""

from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, ForecastSnapshot, Opportunity, User
from app.models.enums import OpportunityStage
from app.services import forecast_service
from app.services.forecast_service import MIN_TREND_WEEKS, linear_trend
from tests.conftest import RoleUsers

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


async def _seed_opp(
    session: AsyncSession,
    owner: User,
    name: str,
    amount: str,
    stage: OpportunityStage,
    probability: int,
) -> Opportunity:
    account = Account(name=f"{name}-客户", owner_id=owner.id)
    session.add(account)
    await session.flush()
    opp = Opportunity(
        account_id=account.id,
        name=name,
        amount=Decimal(amount),
        stage=stage,
        probability=probability,
        owner_id=owner.id,
    )
    session.add(opp)
    await session.commit()
    return opp


async def test_weighted_pipeline_math_and_rbac(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    # sales_a：proposal 100000×50% + negotiation 200000×70% = 190000；won 不计入
    await _seed_opp(session, roles.sales_a, "A1", "100000", OpportunityStage.PROPOSAL, 50)
    await _seed_opp(session, roles.sales_a, "A2", "200000", OpportunityStage.NEGOTIATION, 70)
    await _seed_opp(session, roles.sales_a, "A3", "999999", OpportunityStage.WON, 100)
    # sales_b（另一团队）：initial 50000×10% = 5000
    await _seed_opp(session, roles.sales_b, "B1", "50000", OpportunityStage.INITIAL, 10)

    resp = await client.get("/api/v1/forecast", headers=await login("sales_a@test.cn"))
    body = resp.json()
    assert body["pipeline"]["open_count"] == 2
    assert body["pipeline"]["total_amount"] == 300000
    assert body["pipeline"]["weighted_amount"] == 190000
    by_stage = {b["stage"]: b for b in body["pipeline"]["by_stage"]}
    assert by_stage["proposal"]["weighted"] == 50000
    assert by_stage["negotiation"]["weighted"] == 140000
    # 数据不足 → trend 为 null 且 data_note 说明
    assert body["trend"] is None
    assert "不足" in body["data_note"]

    # manager 看团队（= sales_a 数据）；admin 看全公司（含 sales_b）
    resp = await client.get("/api/v1/forecast", headers=await login("manager_a@test.cn"))
    assert resp.json()["pipeline"]["weighted_amount"] == 190000
    resp = await client.get("/api/v1/forecast", headers=await login("admin@test.cn"))
    assert resp.json()["pipeline"]["weighted_amount"] == 195000


async def test_snapshot_idempotent_and_history_scope(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    await _seed_opp(session, roles.sales_a, "A1", "100000", OpportunityStage.PROPOSAL, 50)
    await _seed_opp(session, roles.sales_b, "B1", "60000", OpportunityStage.INITIAL, 10)

    count = await forecast_service.take_snapshots(session, date(2026, 7, 13))
    assert count == 2  # 两个 owner 各一条
    # 同日重跑：覆盖不新增
    count = await forecast_service.take_snapshots(session, date(2026, 7, 13))
    assert count == 2
    total_rows = await session.scalar(select(func.count()).select_from(ForecastSnapshot))
    assert total_rows == 2

    # sales_a 只见自己的快照聚合
    resp = await client.get("/api/v1/forecast", headers=await login("sales_a@test.cn"))
    snaps = resp.json()["snapshots"]
    assert len(snaps) == 1
    assert snaps[0]["weighted_amount"] == 50000
    # admin 聚合两人
    resp = await client.get("/api/v1/forecast", headers=await login("admin@test.cn"))
    assert resp.json()["snapshots"][0]["weighted_amount"] == 56000


async def test_snapshot_endpoint_rbac(
    client: AsyncClient, roles: RoleUsers, login: LoginFn, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typing import Any

    from app.tasks import dispatcher

    calls: list[str] = []

    async def fake_enqueue(task_name: str, *args: Any) -> bool:
        calls.append(task_name)
        return True

    monkeypatch.setattr(dispatcher, "enqueue", fake_enqueue)

    resp = await client.post("/api/v1/forecast/snapshot", headers=await login("sales_a@test.cn"))
    assert resp.status_code == 403
    resp = await client.post("/api/v1/forecast/snapshot", headers=await login("manager_a@test.cn"))
    assert resp.status_code == 202
    assert calls == ["forecast_snapshot_task"]


async def test_linear_trend_guard_and_extrapolation(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    # 纯函数守卫：不足 MIN_TREND_WEEKS 期返回 None
    assert linear_trend([100.0] * (MIN_TREND_WEEKS - 1)) is None
    # 稳定线性增长：外推值≈下一期，区间收窄
    series = [10000.0 + 500 * i for i in range(MIN_TREND_WEEKS)]
    trend = linear_trend(series)
    assert trend is not None
    assert abs(trend["next_weighted"] - (10000 + 500 * MIN_TREND_WEEKS)) < 1
    assert trend["lower"] <= trend["next_weighted"] <= trend["upper"]

    # 端到端：mock 26 周快照 → trend 非 null 且 data_note 标注方法
    for i in range(MIN_TREND_WEEKS):
        session.add(
            ForecastSnapshot(
                snapshot_date=date(2026, 1, 5) + timedelta(weeks=i),
                owner_id=roles.sales_a.id,
                total_amount=Decimal(200000),
                weighted_amount=Decimal(10000 + 500 * i),
                open_count=3,
                by_stage={},
            )
        )
    await session.commit()
    resp = await client.get("/api/v1/forecast", headers=await login("sales_a@test.cn"))
    body = resp.json()
    assert body["trend"] is not None
    assert body["trend"]["method"] == "least_squares"
    assert "线性外推" in body["data_note"]
