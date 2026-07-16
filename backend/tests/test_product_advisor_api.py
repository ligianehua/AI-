"""M14 产品咨询助手：工具循环 SSE、知识库无据提示、工具容错。"""

import json
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, get_llm_client
from app.main import app
from app.models import Product
from tests.conftest import RoleUsers
from tests.fake_llm import FakeOpenAI, completion, tool_call

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


@pytest.fixture(autouse=True)
def _inject_llm(llm: LLMClient) -> Any:
    app.dependency_overrides[get_llm_client] = lambda: llm
    yield
    app.dependency_overrides.pop(get_llm_client, None)


def _parse_sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = block.strip().split("\n")
        event = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


async def test_detail_tool_and_sse(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    fakes: dict[str, FakeOpenAI],
) -> None:
    session.add(
        Product(
            model_no="VFD-750B",
            name="750W 变频器",
            category="变频器",
            specs={"额定功率": "750W", "输入电压": "380V"},
            created_by=roles.admin.id,
        )
    )
    await session.commit()

    fakes["deepseek"].chat.completions.responses = [
        completion(
            "", tool_calls=[tool_call("c1", "get_product_detail", '{"model_no": "VFD-750B"}')]
        ),
        completion("VFD-750B 额定功率 750W，输入电压 380V。"),
    ]
    headers = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/product-advisor/chat",
        json={"message": "VFD-750B 的功率是多少？"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert [e for e, _ in events] == ["tool", "delta", "done"]
    assert events[0][1]["name"] == "get_product_detail"
    assert "750W" in events[1][1]["text"]

    # 工具结果注入了真实参数
    tool_msg = next(
        m for m in fakes["deepseek"].chat.completions.calls[1]["messages"] if m["role"] == "tool"
    )
    assert "额定功率" in tool_msg["content"]
    assert "750W" in tool_msg["content"]


async def test_knowledge_empty_returns_escalation_hint(
    client: AsyncClient, roles: RoleUsers, login: LoginFn, fakes: dict[str, FakeOpenAI]
) -> None:
    """售后问题知识库无据 → 工具结果里带「转人工」指令（prompt 安全红线的数据面）。"""
    fakes["deepseek"].chat.completions.responses = [
        completion("", tool_calls=[tool_call("c1", "search_knowledge", '{"query": "E99 报错"}')]),
        completion("知识库暂无该报错的处理记录，建议转人工工程师处理。"),
    ]
    headers = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/product-advisor/chat", json={"message": "设备报 E99 怎么办？"}, headers=headers
    )
    events = _parse_sse(resp.text)
    assert [e for e, _ in events] == ["tool", "delta", "done"]

    tool_msg = next(
        m for m in fakes["deepseek"].chat.completions.calls[1]["messages"] if m["role"] == "tool"
    )
    assert "转人工" in tool_msg["content"]  # 无据时工具明确指示按铁律回复


async def test_compare_tool_missing_models(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    fakes: dict[str, FakeOpenAI],
) -> None:
    session.add(
        Product(model_no="A-1", name="产品A", specs={"功率": "1kW"}, created_by=roles.admin.id)
    )
    await session.commit()

    fakes["deepseek"].chat.completions.responses = [
        completion(
            "",
            tool_calls=[tool_call("c1", "compare_products", '{"model_nos": ["A-1", "GHOST-9"]}')],
        ),
        completion("库里只有 A-1，GHOST-9 未收录，无法对比。"),
    ]
    headers = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/product-advisor/chat",
        json={"message": "对比 A-1 和 GHOST-9"},
        headers=headers,
    )
    events = _parse_sse(resp.text)
    assert [e for e, _ in events] == ["tool", "delta", "done"]
    tool_msg = next(
        m for m in fakes["deepseek"].chat.completions.calls[1]["messages"] if m["role"] == "tool"
    )
    assert "不足 2 个" in tool_msg["content"]
    assert "GHOST-9" in tool_msg["content"]
