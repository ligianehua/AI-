"""客户/联系人 API 测试：CRUD + 三角色 RBAC + 时间线聚合。"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Activity, Lead, Opportunity, User
from app.models.enums import (
    ActivityRelatedType,
    ActivityType,
    LeadSource,
    LeadStatus,
    OpportunityStage,
)
from app.tasks import dispatcher
from tests.conftest import RoleUsers

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


async def _seed_account(session: AsyncSession, owner: User, name: str | None = None) -> Account:
    account = Account(name=name or f"客户-{uuid.uuid4().hex[:6]}", owner_id=owner.id)
    session.add(account)
    await session.commit()
    return account


async def test_account_crud_and_rbac(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    headers_a = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/accounts",
        json={"name": "360测试客户", "industry": "制造业", "region": "华东"},
        headers=headers_a,
    )
    assert resp.status_code == 201
    account_id = resp.json()["id"]

    await _seed_account(session, roles.sales_a2)
    await _seed_account(session, roles.sales_b)

    # sales 只见自己；manager 见团队；admin 全量
    resp = await client.get("/api/v1/accounts", headers=headers_a)
    assert resp.json()["total"] == 1
    resp = await client.get("/api/v1/accounts", headers=await login("manager_a@test.cn"))
    assert resp.json()["total"] == 2
    resp = await client.get("/api/v1/accounts", headers=await login("admin@test.cn"))
    assert resp.json()["total"] == 3

    # 名称搜索
    resp = await client.get("/api/v1/accounts?q=360测试", headers=headers_a)
    assert resp.json()["total"] == 1

    # 跨可见域取详情 404
    resp = await client.get(
        f"/api/v1/accounts/{account_id}", headers=await login("sales_b@test.cn")
    )
    assert resp.status_code == 404

    # 更新
    resp = await client.patch(
        f"/api/v1/accounts/{account_id}", json={"size": "201-500人"}, headers=headers_a
    )
    assert resp.status_code == 200
    assert resp.json()["size"] == "201-500人"


async def test_contact_crud_scoped_by_account(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    account_a = await _seed_account(session, roles.sales_a)
    headers_a = await login("sales_a@test.cn")
    headers_b = await login("sales_b@test.cn")

    resp = await client.post(
        "/api/v1/contacts",
        json={
            "account_id": str(account_a.id),
            "name": "王决策",
            "title": "总经理",
            "role_in_deal": "decision_maker",
        },
        headers=headers_a,
    )
    assert resp.status_code == 201
    contact_id = resp.json()["id"]

    # 别人的客户不能加联系人 / 改 / 删（404 不泄露存在性）
    resp = await client.post(
        "/api/v1/contacts",
        json={"account_id": str(account_a.id), "name": "越权联系人"},
        headers=headers_b,
    )
    assert resp.status_code == 404
    resp = await client.patch(
        f"/api/v1/contacts/{contact_id}", json={"title": "副总"}, headers=headers_b
    )
    assert resp.status_code == 404

    # 本人可改可删
    resp = await client.patch(
        f"/api/v1/contacts/{contact_id}", json={"title": "副总经理"}, headers=headers_a
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "副总经理"

    resp = await client.delete(f"/api/v1/contacts/{contact_id}", headers=headers_a)
    assert resp.status_code == 204
    resp = await client.get(f"/api/v1/accounts/{account_a.id}", headers=headers_a)
    assert resp.json()["contacts"] == []


async def test_timeline_aggregates_lead_and_opportunity(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    """时间线必须包含：转化前线索的记录 + 客户直挂记录 + 商机记录。"""
    owner = roles.sales_a
    account = await _seed_account(session, owner, name="时间线客户")
    lead = Lead(
        source=LeadSource.REFERRAL,
        account_name="时间线客户（线索期）",
        status=LeadStatus.CONVERTED,
        owner_id=owner.id,
        converted_account_id=account.id,
    )
    opp = Opportunity(
        account_id=account.id,
        name="时间线商机",
        stage=OpportunityStage.PROPOSAL,
        owner_id=owner.id,
        stage_history=[],
    )
    session.add_all([lead, opp])
    await session.flush()

    def act(rtype: ActivityRelatedType, rid: uuid.UUID, content: str) -> Activity:
        return Activity(
            related_type=rtype,
            related_id=rid,
            type=ActivityType.CALL,
            content=content,
            owner_id=owner.id,
        )

    session.add_all(
        [
            act(ActivityRelatedType.LEAD, lead.id, "转化前的线索沟通"),
            act(ActivityRelatedType.ACCOUNT, account.id, "客户拜访记录"),
            act(ActivityRelatedType.OPPORTUNITY, opp.id, "商机报价沟通"),
        ]
    )
    # 无关记录不应出现
    other_account = await _seed_account(session, roles.sales_b)
    session.add(act(ActivityRelatedType.ACCOUNT, other_account.id, "别人的记录"))
    await session.commit()

    headers = await login("sales_a@test.cn")
    resp = await client.get(f"/api/v1/accounts/{account.id}/timeline", headers=headers)
    assert resp.status_code == 200
    items = resp.json()
    contents = {i["content"] for i in items}
    assert contents == {"转化前的线索沟通", "客户拜访记录", "商机报价沟通"}
    labels = {i["related_label"] for i in items}
    assert "线索：时间线客户（线索期）" in labels
    assert "商机：时间线商机" in labels
    assert "客户跟进" in labels
    assert all(i["owner_name"] == "A组销售一" for i in items)


async def test_trigger_profile_enqueues(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_enqueue(task_name: str, *args: Any) -> None:
        calls.append((task_name, args))

    monkeypatch.setattr(dispatcher, "enqueue", fake_enqueue)
    account = await _seed_account(session, roles.sales_a)

    headers = await login("sales_a@test.cn")
    resp = await client.post(f"/api/v1/accounts/{account.id}/profile", headers=headers)
    assert resp.status_code == 202
    assert calls == [("account_profile_task", (str(account.id),))]

    # 别人的客户不能触发
    resp = await client.post(
        f"/api/v1/accounts/{account.id}/profile", headers=await login("sales_b@test.cn")
    )
    assert resp.status_code == 404
