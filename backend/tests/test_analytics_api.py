"""M12 业绩分析：指标口径、月份归属、RBAC、AI 归因（mock LLM）。"""

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, get_llm_client
from app.main import app
from app.models import Account, Activity, Opportunity, User
from app.models.enums import ActivityRelatedType, ActivityType, OpportunityStage
from tests.conftest import RoleUsers
from tests.fake_llm import FakeOpenAI, completion

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


@pytest.fixture(autouse=True)
def _inject_llm(llm: LLMClient) -> Any:
    app.dependency_overrides[get_llm_client] = lambda: llm
    yield
    app.dependency_overrides.pop(get_llm_client, None)


async def _seed_closed_opp(
    session: AsyncSession,
    owner: User,
    name: str,
    amount: str,
    stage: OpportunityStage,
    entered_at: datetime,
    created_at: datetime | None = None,
) -> Opportunity:
    account = Account(name=f"{name}-客户", owner_id=owner.id)
    session.add(account)
    await session.flush()
    opp = Opportunity(
        account_id=account.id,
        name=name,
        amount=Decimal(amount),
        stage=stage,
        owner_id=owner.id,
        stage_history=[
            {"stage": stage.value, "entered_at": entered_at.isoformat(), "by": owner.name}
        ],
    )
    session.add(opp)
    await session.flush()
    if created_at is not None:
        opp.created_at = created_at
    await session.commit()
    return opp


async def test_month_metrics_and_rbac(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    # sales_a：6 月赢 1 单（20 万，周期 10 天）、丢 1 单；7 月赢 1 单（30 万）
    await _seed_closed_opp(
        session,
        roles.sales_a,
        "六月赢单",
        "200000",
        OpportunityStage.WON,
        datetime(2026, 6, 20, tzinfo=UTC),
        created_at=datetime(2026, 6, 10, tzinfo=UTC),
    )
    await _seed_closed_opp(
        session,
        roles.sales_a,
        "六月丢单",
        "80000",
        OpportunityStage.LOST,
        datetime(2026, 6, 25, tzinfo=UTC),
    )
    await _seed_closed_opp(
        session,
        roles.sales_a,
        "七月赢单",
        "300000",
        OpportunityStage.WON,
        datetime(2026, 7, 5, tzinfo=UTC),
        created_at=datetime(2026, 6, 5, tzinfo=UTC),
    )
    # sales_b（另一团队）：7 月赢 1 单，不该进 sales_a/manager_a 的口径
    await _seed_closed_opp(
        session,
        roles.sales_b,
        "他队赢单",
        "999000",
        OpportunityStage.WON,
        datetime(2026, 7, 8, tzinfo=UTC),
    )
    session.add(
        Activity(
            related_type=ActivityRelatedType.ACCOUNT,
            related_id=roles.sales_a.id,
            type=ActivityType.CALL,
            content="七月的跟进",
            owner_id=roles.sales_a.id,
            created_at=datetime(2026, 7, 2, tzinfo=UTC),
        )
    )
    await session.commit()

    headers = await login("sales_a@test.cn")
    resp = await client.get(
        "/api/v1/analytics/performance", params={"month": "2026-07"}, headers=headers
    )
    body = resp.json()
    cur, prev = body["current"], body["previous"]
    assert cur["month"] == "2026-07"
    assert cur["won_amount"] == 300000
    assert cur["won_count"] == 1
    assert cur["win_rate"] == 100.0
    assert cur["avg_cycle_days"] == 30.0
    assert cur["activity_count"] == 1
    assert prev["month"] == "2026-06"
    assert prev["won_amount"] == 200000
    assert prev["win_rate"] == 50.0  # 1 won / 2 closed
    assert prev["avg_cycle_days"] == 10.0

    # admin 全公司口径含 sales_b 的 7 月赢单
    resp = await client.get(
        "/api/v1/analytics/performance",
        params={"month": "2026-07"},
        headers=await login("admin@test.cn"),
    )
    assert resp.json()["current"]["won_amount"] == 1299000

    # 无关闭商机的月份：win_rate 为 null
    resp = await client.get(
        "/api/v1/analytics/performance", params={"month": "2026-01"}, headers=headers
    )
    assert resp.json()["current"]["win_rate"] is None

    # 非法月份格式
    resp = await client.get(
        "/api/v1/analytics/performance", params={"month": "2026/07"}, headers=headers
    )
    assert resp.status_code == 400


async def test_insight_uses_llm_with_metrics_in_prompt(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    fakes: dict[str, FakeOpenAI],
) -> None:
    await _seed_closed_opp(
        session,
        roles.sales_a,
        "赢单",
        "500000",
        OpportunityStage.WON,
        datetime(2026, 7, 3, tzinfo=UTC),
    )
    insight_json = json.dumps(
        {
            "summary": "本月成交 50 万元，环比上月无成交显著提升。",
            "findings": ["成交额 500000 元，上月为 0，无对比基础"],
            "suggestions": ["保持当前跟进节奏"],
        },
        ensure_ascii=False,
    )
    fakes["deepseek"].chat.completions.responses = [completion(insight_json)]

    headers = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/analytics/insight", params={"month": "2026-07"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "50 万" in body["summary"] or "500000" in body["summary"]
    assert len(body["findings"]) >= 1

    # prompt 里带上了真实指标 JSON（本月成交额）与视角
    sent = fakes["deepseek"].chat.completions.calls[0]["messages"][0]["content"]
    assert '"won_amount": 500000.0' in sent
    assert "个人业绩" in sent
