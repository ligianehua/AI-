"""跟进记录 API 测试：三种宿主实体、越权 404、线索跟进自动重算评分、本人才能改删。"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Lead, User
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


async def _seed_lead(session: AsyncSession, owner: User) -> Lead:
    lead = Lead(
        source=LeadSource.WEBSITE,
        account_name=f"公司-{uuid.uuid4().hex[:6]}",
        status=LeadStatus.NEW,
        owner_id=owner.id,
    )
    session.add(lead)
    await session.commit()
    return lead


async def _seed_account(session: AsyncSession, owner: User) -> Account:
    account = Account(name=f"客户-{uuid.uuid4().hex[:6]}", owner_id=owner.id)
    session.add(account)
    await session.commit()
    return account


async def test_create_activity_on_lead_triggers_rescore(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    enqueued: list[tuple[str, tuple[Any, ...]]],
) -> None:
    lead = await _seed_lead(session, roles.sales_a)
    headers = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/activities",
        json={
            "related_type": "lead",
            "related_id": str(lead.id),
            "type": "call",
            "content": "电话沟通，客户确认预算 20 万",
            "next_action": "发送方案",
            "next_action_date": "2026-07-20",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["owner_name"] == "A组销售一"
    # 线索新增跟进 → 自动重算评分
    assert enqueued == [("score_lead_task", (str(lead.id),))]


async def test_create_activity_on_account_no_rescore(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    enqueued: list[tuple[str, tuple[Any, ...]]],
) -> None:
    account = await _seed_account(session, roles.sales_a)
    headers = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/activities",
        json={
            "related_type": "account",
            "related_id": str(account.id),
            "type": "visit",
            "content": "上门拜访",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert enqueued == []


async def test_activity_cross_scope_rejected(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    lead = await _seed_lead(session, roles.sales_a)
    resp = await client.post(
        "/api/v1/activities",
        json={
            "related_type": "lead",
            "related_id": str(lead.id),
            "type": "call",
            "content": "越权跟进",
        },
        headers=await login("sales_b@test.cn"),
    )
    assert resp.status_code == 404

    resp = await client.get(
        f"/api/v1/activities?related_type=lead&related_id={lead.id}",
        headers=await login("sales_b@test.cn"),
    )
    assert resp.status_code == 404


async def test_list_update_delete_activity(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    account = await _seed_account(session, roles.sales_a)
    headers_a = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/activities",
        json={
            "related_type": "account",
            "related_id": str(account.id),
            "type": "wechat",
            "content": "微信沟通记录",
        },
        headers=headers_a,
    )
    activity_id = resp.json()["id"]

    resp = await client.get(
        f"/api/v1/activities?related_type=account&related_id={account.id}", headers=headers_a
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # manager 可见（同团队），但不能改别人的记录
    headers_m = await login("manager_a@test.cn")
    resp = await client.get(
        f"/api/v1/activities?related_type=account&related_id={account.id}", headers=headers_m
    )
    assert resp.status_code == 200
    resp = await client.patch(
        f"/api/v1/activities/{activity_id}", json={"content": "改别人的"}, headers=headers_m
    )
    assert resp.status_code == 403

    # 本人可改可删
    resp = await client.patch(
        f"/api/v1/activities/{activity_id}", json={"content": "修改后的内容"}, headers=headers_a
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "修改后的内容"

    resp = await client.delete(f"/api/v1/activities/{activity_id}", headers=headers_a)
    assert resp.status_code == 204
    resp = await client.get(
        f"/api/v1/activities?related_type=account&related_id={account.id}", headers=headers_a
    )
    assert resp.json() == []
