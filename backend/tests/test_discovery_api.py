"""M8 线索发现：订阅 CRUD/RBAC、抓取入池幂等与撞单提示、领取转线索事务。"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models import DiscoveryCandidate, DiscoverySubscription, Lead, User
from app.models.enums import CandidateStatus, LeadSource
from app.services import discovery_service
from app.services.google_places import PlaceResult
from app.tasks import dispatcher
from app.tasks.discovery import run_discovery_task
from tests.conftest import RoleUsers

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


@pytest.fixture(autouse=True)
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[Any, ...]]]:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_enqueue(task_name: str, *args: Any) -> bool:
        calls.append((task_name, args))
        return True

    monkeypatch.setattr(dispatcher, "enqueue", fake_enqueue)
    return calls


def _places(*specs: tuple[str, str, str | None]) -> list[PlaceResult]:
    return [
        PlaceResult(place_id=pid, name=name, phone=phone, address="Jl. Test No.1", website=None)
        for pid, name, phone in specs
    ]


async def _make_subscription(
    session: AsyncSession, owner: User, **overrides: Any
) -> DiscoverySubscription:
    fields: dict[str, Any] = {
        "name": "雅加达 制造业",
        "country": "Indonesia",
        "city": "Jakarta",
        "category": "manufacturing",
        "owner_id": owner.id,
    }
    fields.update(overrides)
    sub = DiscoverySubscription(**fields)
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


# ---------- 订阅 CRUD + RBAC ----------


async def test_subscription_crud_and_rbac(
    client: AsyncClient, roles: RoleUsers, login: LoginFn
) -> None:
    headers_a = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/discovery/subscriptions",
        json={"country": "Indonesia", "city": "Jakarta", "category": "manufacturing"},
        headers=headers_a,
    )
    assert resp.status_code == 201, resp.text
    sub = resp.json()
    assert sub["name"] == "Jakarta manufacturing"  # 未填名称自动生成
    assert sub["is_active"] is True

    # 本人可见
    resp = await client.get("/api/v1/discovery/subscriptions", headers=headers_a)
    assert resp.json()["total"] == 1

    # 跨团队销售不可见、不可改（404 不泄露存在性）
    headers_b = await login("sales_b@test.cn")
    resp = await client.get("/api/v1/discovery/subscriptions", headers=headers_b)
    assert resp.json()["total"] == 0
    resp = await client.patch(
        f"/api/v1/discovery/subscriptions/{sub['id']}",
        json={"is_active": False},
        headers=headers_b,
    )
    assert resp.status_code == 404

    # 同团队主管可见；admin 可见
    for email in ("manager_a@test.cn", "admin@test.cn"):
        resp = await client.get("/api/v1/discovery/subscriptions", headers=await login(email))
        assert resp.json()["total"] == 1, email

    # 更新与软删
    resp = await client.patch(
        f"/api/v1/discovery/subscriptions/{sub['id']}",
        json={"is_active": False, "keyword": "factory"},
        headers=headers_a,
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    resp = await client.delete(f"/api/v1/discovery/subscriptions/{sub['id']}", headers=headers_a)
    assert resp.status_code == 204
    resp = await client.get("/api/v1/discovery/subscriptions", headers=headers_a)
    assert resp.json()["total"] == 0


async def test_run_endpoint_enqueues_and_guards(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    enqueued: list[tuple[str, tuple[Any, ...]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sub = await _make_subscription(session, roles.sales_a)
    headers = await login("sales_a@test.cn")

    # 单测不依赖 .env 里的真实 key（CI 无 .env）：显式给 settings 单例注入假 key
    monkeypatch.setattr(get_settings(), "google_maps_api_key", "unit-test-key")
    resp = await client.post(f"/api/v1/discovery/subscriptions/{sub.id}/run", headers=headers)
    assert resp.status_code == 202, resp.text
    assert resp.json()["enqueued"] is True
    assert enqueued == [("run_discovery_task", (str(sub.id),))]

    # 停用后拒绝
    sub.is_active = False
    await session.commit()
    resp = await client.post(f"/api/v1/discovery/subscriptions/{sub.id}/run", headers=headers)
    assert resp.status_code == 400
    assert "停用" in resp.json()["message"]

    # key 缺失给可读中文错误
    sub.is_active = True
    await session.commit()
    monkeypatch.setattr(get_settings(), "google_maps_api_key", "")
    resp = await client.post(f"/api/v1/discovery/subscriptions/{sub.id}/run", headers=headers)
    assert resp.status_code == 400
    assert "GOOGLE_MAPS_API_KEY" in resp.json()["message"]


# ---------- 抓取入池 ----------


async def test_ingest_idempotent_and_duplicate_hint(
    session: AsyncSession, roles: RoleUsers
) -> None:
    # 库内已有同电话线索 → 撞单提示
    session.add(
        Lead(
            source=LeadSource.WEBSITE,
            account_name="已有线索公司",
            contact_phone="+62 21 555001",
            owner_id=roles.sales_a.id,
        )
    )
    await session.commit()
    sub = await _make_subscription(session, roles.sales_a)

    places = _places(
        ("place-1", "PT Alpha", "+62 21 555001"),
        ("place-2", "PT Beta", None),
    )
    new_count = await discovery_service.ingest_places(session, sub, places)
    assert new_count == 2
    await session.refresh(sub)
    assert sub.last_run_new == 2
    assert sub.last_run_at is not None

    rows = {c.place_id: c for c in (await session.scalars(select(DiscoveryCandidate))).all()}
    assert rows["place-1"].duplicate_hint is not None
    assert "同电话" in rows["place-1"].duplicate_hint
    assert rows["place-2"].duplicate_hint is None
    assert rows["place-1"].owner_id == roles.sales_a.id

    # 同一批再跑一次：place_id 幂等，全部跳过
    new_count = await discovery_service.ingest_places(session, sub, places)
    assert new_count == 0
    await session.refresh(sub)
    assert sub.last_run_new == 0


async def test_run_discovery_task_with_fake_places(
    engine: AsyncEngine, session: AsyncSession, roles: RoleUsers
) -> None:
    sub = await _make_subscription(session, roles.sales_a, keyword="metal")

    class FakePlaces:
        def __init__(self) -> None:
            self.queries: list[str] = []

        async def search_text(self, query: str, max_results: int = 20) -> list[PlaceResult]:
            self.queries.append(query)
            return _places(("place-t1", "PT Gamma", None))

    fake = FakePlaces()
    maker = async_sessionmaker(engine, expire_on_commit=False)
    await run_discovery_task({"sessionmaker": maker, "places": fake}, str(sub.id))

    assert fake.queries == ["metal manufacturing in Jakarta, Indonesia"]
    count = len((await session.scalars(select(DiscoveryCandidate))).all())
    assert count == 1


# ---------- 候选池：领取 / 忽略 / RBAC ----------


async def _seed_candidate(
    session: AsyncSession, sub: DiscoverySubscription, **overrides: Any
) -> DiscoveryCandidate:
    fields: dict[str, Any] = {
        "subscription_id": sub.id,
        "place_id": f"place-{uuid.uuid4().hex[:8]}",
        "name": "PT Candidate",
        "phone": "+62 21 777888",
        "address": "Jl. Sudirman No.9",
        "website": "https://example.co.id",
        "country": sub.country,
        "city": sub.city,
        "category": sub.category,
        "owner_id": sub.owner_id,
    }
    fields.update(overrides)
    candidate = DiscoveryCandidate(**fields)
    session.add(candidate)
    await session.commit()
    await session.refresh(candidate)
    return candidate


async def test_claim_creates_lead_and_enqueues_scoring(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    enqueued: list[tuple[str, tuple[Any, ...]]],
) -> None:
    sub = await _make_subscription(session, roles.sales_a)
    candidate = await _seed_candidate(session, sub)
    headers = await login("sales_a@test.cn")

    resp = await client.post(f"/api/v1/discovery/candidates/{candidate.id}/claim", headers=headers)
    assert resp.status_code == 200, resp.text
    lead_id = resp.json()["lead_id"]
    assert enqueued == [("score_lead_task", (lead_id,))]

    lead = await session.get(Lead, uuid.UUID(lead_id))
    assert lead is not None
    assert lead.source == LeadSource.DISCOVERY
    assert lead.account_name == "PT Candidate"
    assert lead.contact_phone == "+62 21 777888"
    assert lead.owner_id == roles.sales_a.id
    assert lead.requirement_desc is not None and "Jakarta" in lead.requirement_desc

    await session.refresh(candidate)
    assert candidate.status == CandidateStatus.CLAIMED
    assert candidate.claimed_lead_id == uuid.UUID(lead_id)

    # 重复领取被拦；已领取不能忽略
    resp = await client.post(f"/api/v1/discovery/candidates/{candidate.id}/claim", headers=headers)
    assert resp.status_code == 409
    resp = await client.post(f"/api/v1/discovery/candidates/{candidate.id}/ignore", headers=headers)
    assert resp.status_code == 409

    # 线索列表可见（含来源）
    resp = await client.get("/api/v1/leads", headers=headers)
    sources = [item["source"] for item in resp.json()["items"]]
    assert "discovery" in sources


async def test_candidate_rbac_and_ignore(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    sub = await _make_subscription(session, roles.sales_a)
    candidate = await _seed_candidate(session, sub)

    # 跨团队：列表不可见，操作 404
    headers_b = await login("sales_b@test.cn")
    resp = await client.get("/api/v1/discovery/candidates", headers=headers_b)
    assert resp.json()["total"] == 0
    for action in ("claim", "ignore"):
        resp = await client.post(
            f"/api/v1/discovery/candidates/{candidate.id}/{action}", headers=headers_b
        )
        assert resp.status_code == 404, action

    # 同团队主管可见并可忽略
    headers_m = await login("manager_a@test.cn")
    resp = await client.get("/api/v1/discovery/candidates", headers=headers_m)
    assert resp.json()["total"] == 1
    resp = await client.post(
        f"/api/v1/discovery/candidates/{candidate.id}/ignore", headers=headers_m
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"

    # 状态筛选
    headers_a = await login("sales_a@test.cn")
    resp = await client.get(
        "/api/v1/discovery/candidates", params={"status": "pending"}, headers=headers_a
    )
    assert resp.json()["total"] == 0
    resp = await client.get(
        "/api/v1/discovery/candidates", params={"status": "ignored"}, headers=headers_a
    )
    assert resp.json()["total"] == 1
