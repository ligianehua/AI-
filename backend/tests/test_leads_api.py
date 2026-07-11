"""线索 API 测试：CRUD / RBAC / 查重 / 转化事务 / 批量分配。评分入队被 mock。"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Contact, Lead, Opportunity, User
from app.models.enums import LeadSource, LeadStatus
from app.tasks import dispatcher
from tests.conftest import RoleUsers

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


@pytest.fixture(autouse=True)
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[Any, ...]]]:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_enqueue(task_name: str, *args: Any) -> None:
        calls.append((task_name, args))

    monkeypatch.setattr(dispatcher, "enqueue", fake_enqueue)
    return calls


def _payload(**kwargs: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source": "referral",
        "account_name": "上海创新科技",
        "contact_name": "刘总",
        "contact_phone": "13900000001",
        "requirement_desc": "需要销售管理系统，预算 15 万",
    }
    base.update(kwargs)
    return base


async def _seed_lead(
    session: AsyncSession, owner: User, *, score: int | None = None, **kwargs: Any
) -> Lead:
    defaults: dict[str, Any] = {
        "source": LeadSource.WEBSITE,
        "account_name": f"公司-{uuid.uuid4().hex[:6]}",
        "status": LeadStatus.NEW,
    }
    defaults.update(kwargs)
    lead = Lead(**defaults, owner_id=owner.id, score=score)
    session.add(lead)
    await session.commit()
    return lead


async def test_create_lead_triggers_scoring(
    client: AsyncClient,
    roles: RoleUsers,
    login: LoginFn,
    enqueued: list[tuple[str, tuple[Any, ...]]],
) -> None:
    headers = await login("sales_a@test.cn")
    resp = await client.post("/api/v1/leads", json=_payload(), headers=headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["lead"]["status"] == "new"
    assert body["duplicate_warnings"] == []
    assert enqueued == [("score_lead_task", (body["lead"]["id"],))]


async def test_create_lead_duplicate_warning_cross_owner(
    client: AsyncClient, roles: RoleUsers, login: LoginFn
) -> None:
    headers_b = await login("sales_b@test.cn")
    first = await client.post("/api/v1/leads", json=_payload(), headers=headers_b)
    assert first.status_code == 201

    headers_a = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/leads", json=_payload(account_name="另一家公司"), headers=headers_a
    )
    assert resp.status_code == 201
    warnings = resp.json()["duplicate_warnings"]
    assert len(warnings) == 1
    assert warnings[0]["matched_field"] == "contact_phone"
    assert warnings[0]["owner_name"] == "B组销售"  # 撞单提示跨可见域


async def test_list_leads_scoped_sorted_filtered(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    await _seed_lead(session, roles.sales_a, score=80, status=LeadStatus.CONTACTED)
    await _seed_lead(session, roles.sales_a, score=50)
    await _seed_lead(session, roles.sales_a, score=None)
    await _seed_lead(session, roles.sales_b, score=99)

    headers = await login("sales_a@test.cn")
    resp = await client.get("/api/v1/leads", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3  # 看不到 sales_b 的
    assert [item["score"] for item in body["items"]] == [80, 50, None]  # -score 未评分排最后
    assert body["items"][0]["owner_name"] == "A组销售一"

    resp = await client.get("/api/v1/leads?score_gte=60", headers=headers)
    assert resp.json()["total"] == 1

    resp = await client.get("/api/v1/leads?status=contacted", headers=headers)
    assert resp.json()["total"] == 1

    # manager 看全团队；admin 看全部
    resp = await client.get("/api/v1/leads", headers=await login("manager_a@test.cn"))
    assert resp.json()["total"] == 3
    resp = await client.get("/api/v1/leads", headers=await login("admin@test.cn"))
    assert resp.json()["total"] == 4


async def test_sales_cannot_get_others_lead(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    lead_b = await _seed_lead(session, roles.sales_b)
    headers = await login("sales_a@test.cn")
    resp = await client.get(f"/api/v1/leads/{lead_b.id}", headers=headers)
    assert resp.status_code == 404


async def test_update_lead_status_rules(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    lead = await _seed_lead(session, roles.sales_a)
    headers = await login("sales_a@test.cn")

    resp = await client.patch(
        f"/api/v1/leads/{lead.id}", json={"status": "contacted"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "contacted"

    resp = await client.patch(
        f"/api/v1/leads/{lead.id}", json={"status": "converted"}, headers=headers
    )
    assert resp.status_code == 400  # 转化状态只能走转化接口


async def test_rescore_endpoint(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    enqueued: list[tuple[str, tuple[Any, ...]]],
) -> None:
    lead = await _seed_lead(session, roles.sales_a)
    headers = await login("sales_a@test.cn")
    resp = await client.post(f"/api/v1/leads/{lead.id}/score", headers=headers)
    assert resp.status_code == 202
    assert enqueued == [("score_lead_task", (str(lead.id),))]


async def test_convert_lead_transactional(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    lead = await _seed_lead(
        session,
        roles.sales_a,
        account_name="转化测试公司",
        contact_name="陈总",
        contact_phone="13900000002",
        industry="金融",
    )
    headers = await login("sales_a@test.cn")
    resp = await client.post(
        f"/api/v1/leads/{lead.id}/convert",
        json={"amount": "200000", "opportunity_name": "转化测试公司-CRM 采购"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()

    account = await session.scalar(select(Account).where(Account.id == result["account_id"]))
    assert account is not None
    assert account.name == "转化测试公司"
    assert account.owner_id == roles.sales_a.id
    contact = await session.scalar(select(Contact).where(Contact.id == result["contact_id"]))
    assert contact is not None and contact.phone == "13900000002"
    opp = await session.scalar(
        select(Opportunity).where(Opportunity.id == result["opportunity_id"])
    )
    assert opp is not None and float(opp.amount) == 200000.0
    assert opp.stage_history[0]["stage"] == "initial"

    await session.refresh(lead)
    assert lead.status == LeadStatus.CONVERTED
    assert lead.converted_account_id == account.id

    # 重复转化被拒，且不产生脏数据
    resp = await client.post(f"/api/v1/leads/{lead.id}/convert", json={}, headers=headers)
    assert resp.status_code == 409
    account_count = await session.scalar(select(func.count()).select_from(Account))
    opp_count = await session.scalar(select(func.count()).select_from(Opportunity))
    assert (account_count, opp_count) == (1, 1)


async def test_convert_invalid_lead_rejected(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    lead = await _seed_lead(session, roles.sales_a, status=LeadStatus.INVALID)
    headers = await login("sales_a@test.cn")
    resp = await client.post(f"/api/v1/leads/{lead.id}/convert", json={}, headers=headers)
    assert resp.status_code == 400


async def test_assign_permissions(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    lead = await _seed_lead(session, roles.sales_a)

    # sales 禁止分配
    resp = await client.post(
        "/api/v1/leads/assign",
        json={"lead_ids": [str(lead.id)], "owner_id": str(roles.sales_a2.id)},
        headers=await login("sales_a@test.cn"),
    )
    assert resp.status_code == 403

    # manager 分给外团队成员被拒
    resp = await client.post(
        "/api/v1/leads/assign",
        json={"lead_ids": [str(lead.id)], "owner_id": str(roles.sales_b.id)},
        headers=await login("manager_a@test.cn"),
    )
    assert resp.status_code == 400

    # manager 分给本团队成员成功
    resp = await client.post(
        "/api/v1/leads/assign",
        json={"lead_ids": [str(lead.id)], "owner_id": str(roles.sales_a2.id)},
        headers=await login("manager_a@test.cn"),
    )
    assert resp.status_code == 200
    assert resp.json()["assigned"] == 1
    await session.refresh(lead)
    assert lead.owner_id == roles.sales_a2.id

    # manager 碰不到 B 组的线索
    lead_b = await _seed_lead(session, roles.sales_b)
    resp = await client.post(
        "/api/v1/leads/assign",
        json={"lead_ids": [str(lead_b.id)], "owner_id": str(roles.sales_a.id)},
        headers=await login("manager_a@test.cn"),
    )
    assert resp.status_code == 400
