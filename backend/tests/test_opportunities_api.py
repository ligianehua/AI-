"""商机 API 测试：CRUD / 看板汇总 / 阶段流转强校验 / RBAC。"""

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Opportunity, User
from app.models.enums import OpportunityStage
from tests.conftest import RoleUsers

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


async def _seed_account(session: AsyncSession, owner: User) -> Account:
    account = Account(name=f"客户-{uuid.uuid4().hex[:6]}", owner_id=owner.id)
    session.add(account)
    await session.commit()
    return account


async def _seed_opp(
    session: AsyncSession,
    owner: User,
    account: Account,
    *,
    amount: int = 100_000,
    stage: OpportunityStage = OpportunityStage.INITIAL,
    probability: int | None = None,
) -> Opportunity:
    opp = Opportunity(
        account_id=account.id,
        name=f"商机-{uuid.uuid4().hex[:6]}",
        amount=Decimal(amount),
        stage=stage,
        probability=probability if probability is not None else 10,
        owner_id=owner.id,
        stage_history=[],
    )
    session.add(opp)
    await session.commit()
    return opp


async def test_create_and_get_opportunity(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    account = await _seed_account(session, roles.sales_a)
    headers = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/opportunities",
        json={"account_id": str(account.id), "name": "首个商机", "amount": "300000"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["stage"] == "initial"
    assert body["probability"] == 10
    assert body["account_name"] == account.name
    assert body["stage_history"][0]["stage"] == "initial"

    # 别人的客户下不能建商机
    resp = await client.post(
        "/api/v1/opportunities",
        json={"account_id": str(account.id), "name": "越权商机"},
        headers=await login("sales_b@test.cn"),
    )
    assert resp.status_code == 404


async def test_kanban_grouping_and_amounts(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    account = await _seed_account(session, roles.sales_a)
    await _seed_opp(
        session,
        roles.sales_a,
        account,
        amount=100_000,
        stage=OpportunityStage.INITIAL,
        probability=10,
    )
    await _seed_opp(
        session,
        roles.sales_a,
        account,
        amount=200_000,
        stage=OpportunityStage.INITIAL,
        probability=10,
    )
    await _seed_opp(
        session,
        roles.sales_a,
        account,
        amount=400_000,
        stage=OpportunityStage.PROPOSAL,
        probability=50,
    )
    # 别人的商机不可见
    account_b = await _seed_account(session, roles.sales_b)
    await _seed_opp(session, roles.sales_b, account_b, amount=999_999)

    headers = await login("sales_a@test.cn")
    resp = await client.get("/api/v1/opportunities/kanban", headers=headers)
    assert resp.status_code == 200
    columns = {c["stage"]: c for c in resp.json()["columns"]}
    assert set(columns) == {"initial", "need_confirmed", "proposal", "negotiation", "won", "lost"}

    initial = columns["initial"]
    assert len(initial["items"]) == 2
    assert initial["total_amount"] == 300_000
    assert initial["weighted_amount"] == 30_000  # 10% 概率加权

    proposal = columns["proposal"]
    assert proposal["total_amount"] == 400_000
    assert proposal["weighted_amount"] == 200_000

    # manager 看团队全量
    resp = await client.get(
        "/api/v1/opportunities/kanban", headers=await login("manager_a@test.cn")
    )
    total_items = sum(len(c["items"]) for c in resp.json()["columns"])
    assert total_items == 3

    resp = await client.get("/api/v1/opportunities/kanban", headers=await login("admin@test.cn"))
    assert sum(len(c["items"]) for c in resp.json()["columns"]) == 4


async def test_stage_change_rules(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    account = await _seed_account(session, roles.sales_a)
    opp = await _seed_opp(session, roles.sales_a, account, stage=OpportunityStage.NEGOTIATION)
    headers = await login("sales_a@test.cn")
    url = f"/api/v1/opportunities/{opp.id}/stage"

    # won 不带金额 → 400
    resp = await client.patch(url, json={"stage": "won"}, headers=headers)
    assert resp.status_code == 400
    assert "金额" in resp.json()["message"]

    # lost 不带原因 → 400
    resp = await client.patch(url, json={"stage": "lost"}, headers=headers)
    assert resp.status_code == 400
    assert "原因" in resp.json()["message"]

    # 正常推进
    resp = await client.patch(url, json={"stage": "proposal"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "proposal"
    assert body["probability"] == 50
    assert body["stage_history"][-1]["stage"] == "proposal"
    assert body["stage_history"][-1]["by"] == "A组销售一"

    # 同阶段重复 → 400
    resp = await client.patch(url, json={"stage": "proposal"}, headers=headers)
    assert resp.status_code == 400

    # won 带金额确认
    resp = await client.patch(url, json={"stage": "won", "amount": "520000"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["probability"] == 100
    assert float(body["amount"]) == 520000.0

    # 别人不能动
    resp = await client.patch(
        url, json={"stage": "initial"}, headers=await login("sales_b@test.cn")
    )
    assert resp.status_code == 404


async def test_update_opportunity_fields(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    account = await _seed_account(session, roles.sales_a)
    opp = await _seed_opp(session, roles.sales_a, account)
    headers = await login("sales_a@test.cn")
    resp = await client.patch(
        f"/api/v1/opportunities/{opp.id}",
        json={"amount": "888000", "probability": 35, "expected_close_date": "2026-09-30"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert float(body["amount"]) == 888000.0
    assert body["probability"] == 35
    assert body["expected_close_date"] == "2026-09-30"
