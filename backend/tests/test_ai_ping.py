from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.ai.client import LLMClient, get_llm_client
from app.main import app
from app.models.llm_call import LlmCall
from tests.conftest import RoleUsers
from tests.fake_llm import FakeOpenAI, completion

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


@pytest.fixture
async def ping_llm(llm: LLMClient) -> AsyncIterator[LLMClient]:
    app.dependency_overrides[get_llm_client] = lambda: llm
    yield llm
    app.dependency_overrides.pop(get_llm_client, None)


async def test_ping_ok_and_accounted(
    client: AsyncClient,
    ping_llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
) -> None:
    fakes["deepseek"].chat.completions.responses = [completion("pong")]
    headers = await login("sales_a@test.cn")
    resp = await client.post("/api/v1/ai/ping", json={"message": "ping"}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reply"] == "pong"
    assert body["provider"] == "deepseek"
    assert body["model"] == "deepseek-v4-flash"

    row = await session.scalar(select(LlmCall))
    assert row is not None
    assert row.user_id == roles.sales_a.id
    assert row.task_type == "ping"
    assert row.status == "ok"


async def test_ping_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/ai/ping", json={"message": "ping"})
    assert resp.status_code == 401


async def test_ping_without_any_api_key_returns_503(
    client: AsyncClient,
    engine: AsyncEngine,
    roles: RoleUsers,
    login: LoginFn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未配密钥时优雅报 503 而不是 500。真实 default factory + 空密钥 + 测试库记账。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    real_factory_llm = LLMClient(sessionmaker=maker)
    app.dependency_overrides[get_llm_client] = lambda: real_factory_llm
    try:
        headers = await login("sales_a@test.cn")
        resp = await client.post("/api/v1/ai/ping", json={"message": "ping"}, headers=headers)
        assert resp.status_code == 503
        assert resp.json()["code"] == "llm_unavailable"
    finally:
        app.dependency_overrides.pop(get_llm_client, None)
