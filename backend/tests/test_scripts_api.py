"""话术库 API 测试：权限、CRUD、嵌入任务触发、混合检索（关键词路/向量路）。"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import rag
from app.ai.client import LLMClient
from app.models import Script, User
from app.tasks import dispatcher
from tests.conftest import RoleUsers
from tests.fake_llm import FakeOpenAI, embedding_response

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


@pytest.fixture(autouse=True)
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[Any, ...]]]:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_enqueue(task_name: str, *args: Any) -> None:
        calls.append((task_name, args))

    monkeypatch.setattr(dispatcher, "enqueue", fake_enqueue)
    return calls


async def _seed_script(
    session: AsyncSession,
    creator: User,
    content: str,
    *,
    category: str = "pricing",
    embedding: list[float] | None = None,
) -> Script:
    script = Script(
        category=category,
        scenario=f"场景-{uuid.uuid4().hex[:4]}",
        content=content,
        tags=[],
        created_by=creator.id,
        embedding=embedding,
    )
    session.add(script)
    await session.commit()
    return script


async def test_script_crud_permissions(
    client: AsyncClient,
    roles: RoleUsers,
    login: LoginFn,
    enqueued: list[tuple[str, tuple[Any, ...]]],
) -> None:
    payload = {
        "category": "opening",
        "scenario": "电话开场",
        "content": "您好，我是……",
        "tags": ["电话"],
    }

    # sales 不能管理
    resp = await client.post(
        "/api/v1/scripts", json=payload, headers=await login("sales_a@test.cn")
    )
    assert resp.status_code == 403

    # manager 可以创建，创建触发嵌入任务
    headers_m = await login("manager_a@test.cn")
    resp = await client.post("/api/v1/scripts", json=payload, headers=headers_m)
    assert resp.status_code == 201
    script_id = resp.json()["id"]
    assert enqueued == [("embed_script_task", (script_id,))]

    # 全员可读
    resp = await client.get("/api/v1/scripts", headers=await login("sales_a@test.cn"))
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    # 改内容 → 重嵌入
    resp = await client.patch(
        f"/api/v1/scripts/{script_id}", json={"content": "新内容您好"}, headers=headers_m
    )
    assert resp.status_code == 200
    assert enqueued[-1] == ("embed_script_task", (script_id,))
    assert resp.json()["has_embedding"] is False

    # 删除（软删）
    resp = await client.delete(f"/api/v1/scripts/{script_id}", headers=headers_m)
    assert resp.status_code == 204
    resp = await client.get("/api/v1/scripts", headers=headers_m)
    assert resp.json()["total"] == 0


async def test_keyword_search_without_embeddings(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """嵌入服务不可用时降级纯关键词（pg_trgm）检索。"""
    await _seed_script(session, roles.admin, "客户嫌贵的时候先做价值拆解，再谈折扣申请")
    await _seed_script(session, roles.admin, "初次电话开场要在一分钟内说明来意", category="opening")

    from app.ai.client import get_llm_client as dep
    from app.main import app

    app.dependency_overrides[dep] = lambda: llm  # fakes 无 embed 响应 → embed 抛错 → 降级
    try:
        headers = await login("sales_a@test.cn")
        resp = await client.post(
            "/api/v1/scripts/search",
            json={"query": "客户嫌贵 折扣", "top_k": 5},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        hits = resp.json()
        assert len(hits) >= 1
        assert "价值拆解" in hits[0]["script"]["content"]
    finally:
        app.dependency_overrides.pop(dep, None)


async def test_hybrid_search_vector_ranking(
    session: AsyncSession,
    roles: RoleUsers,
    llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
) -> None:
    """向量路：与查询向量最接近的话术应排前（真 pgvector cosine 计算）。"""
    near = [1.0] + [0.0] * 1023
    far = [0.0, 1.0] + [0.0] * 1022
    s_near = await _seed_script(session, roles.admin, "谈判让步策略甲", embedding=near)
    await _seed_script(session, roles.admin, "谈判让步策略乙", embedding=far)

    fakes["qwen"].embeddings.responses = [embedding_response([[1.0] + [0.0] * 1023])]
    hits = await rag.search_scripts(session, "让步策略", top_k=2, llm=llm)
    assert len(hits) == 2
    assert hits[0].script.id == s_near.id  # 向量近者 RRF 得分更高
