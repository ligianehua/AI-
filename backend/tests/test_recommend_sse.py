"""推荐 SSE 测试：sources（引用可解释/无参考明示）→ delta 流 → done(llm_call_id) → 反馈落库。"""

import json
import uuid
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, get_llm_client
from app.main import app
from app.models import LlmCall, Script, User
from tests.conftest import RoleUsers
from tests.fake_llm import FakeOpenAI, FakeStream, stream_chunk

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


def _parse_sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = block.strip().split("\n")
        event = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        events.append((event, json.loads(data)))
    return events


async def _seed_script(session: AsyncSession, creator: User, content: str) -> Script:
    script = Script(
        category="pricing",
        scenario="价格异议",
        content=content,
        tags=[],
        created_by=creator.id,
    )
    session.add(script)
    await session.commit()
    return script


def _stream_response() -> FakeStream:
    return FakeStream(
        [
            stream_chunk("【候选1】王总，"),
            stream_chunk("咱们算笔账……"),
            stream_chunk(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50)),
        ]
    )


async def test_recommend_sse_with_references(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
) -> None:
    script = await _seed_script(session, roles.admin, "客户嫌贵时先拆解价值再谈折扣，强调时间成本")
    fakes["deepseek"].chat.completions.responses = [_stream_response()]

    app.dependency_overrides[get_llm_client] = lambda: llm
    try:
        headers = await login("sales_a@test.cn")
        resp = await client.post(
            "/api/v1/scripts/recommend",
            json={"scenario": "pricing", "channel": "wechat", "user_hint": "客户嫌贵 折扣"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(resp.text)

        assert events[0][0] == "sources"
        sources = events[0][1]
        assert sources["no_reference"] is False
        assert sources["scripts"][0]["id"] == str(script.id)  # 标注引用了哪条库内话术

        deltas = "".join(d["text"] for e, d in events if e == "delta")
        assert deltas == "【候选1】王总，咱们算笔账……"

        done = events[-1]
        assert done[0] == "done"
        llm_call_id = done[1]["llm_call_id"]
        assert llm_call_id

        # 生成 prompt 里带上了参考话术与渠道文风要求
        prompt = fakes["deepseek"].chat.completions.calls[0]["messages"][0]["content"]
        assert "拆解价值" in prompt
        assert "微信" in prompt

        # 引用的话术 usage_count +1
        await session.refresh(script)
        assert script.usage_count == 1

        # 赞/踩反馈写入 llm_calls.feedback
        resp = await client.post(
            "/api/v1/ai/feedback",
            json={"llm_call_id": llm_call_id, "feedback": 1},
            headers=headers,
        )
        assert resp.status_code == 204
        call = await session.scalar(select(LlmCall).where(LlmCall.id == uuid.UUID(llm_call_id)))
        assert call is not None and call.feedback == 1

        # 别人不能给我的调用记录反馈
        resp = await client.post(
            "/api/v1/ai/feedback",
            json={"llm_call_id": llm_call_id, "feedback": -1},
            headers=await login("sales_b@test.cn"),
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


async def test_recommend_sse_no_reference_fallback(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
) -> None:
    """库内无匹配话术 → 降级纯生成并明示 no_reference。"""
    fakes["deepseek"].chat.completions.responses = [_stream_response()]
    app.dependency_overrides[get_llm_client] = lambda: llm
    try:
        headers = await login("sales_a@test.cn")
        resp = await client.post(
            "/api/v1/scripts/recommend",
            json={"scenario": "retention", "channel": "email"},
            headers=headers,
        )
        events = _parse_sse(resp.text)
        assert events[0][0] == "sources"
        assert events[0][1]["no_reference"] is True
        assert events[0][1]["scripts"] == []
        assert events[-1][0] == "done"
        prompt = fakes["deepseek"].chat.completions.calls[0]["messages"][0]["content"]
        assert "库内无匹配参考" in prompt
        assert "邮件" in prompt
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


async def test_recommend_sse_llm_error_event(
    client: AsyncClient,
    roles: RoleUsers,
    login: LoginFn,
    llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
) -> None:
    """LLM 不可用 → error 事件（而非 500）。"""
    import httpx as _httpx
    import openai

    req = _httpx.Request("POST", "https://fake.test")
    fakes["deepseek"].chat.completions.responses = [openai.APITimeoutError(request=req)]
    fakes["qwen"].chat.completions.responses = [
        openai.APIConnectionError(message="down", request=req)
    ]
    app.dependency_overrides[get_llm_client] = lambda: llm
    try:
        headers = await login("sales_a@test.cn")
        resp = await client.post(
            "/api/v1/scripts/recommend",
            json={"scenario": "opening", "channel": "phone"},
            headers=headers,
        )
        events = _parse_sse(resp.text)
        assert events[-1][0] == "error"
        assert "AI" in events[-1][1]["message"] or "失败" in events[-1][1]["message"]
    finally:
        app.dependency_overrides.pop(get_llm_client, None)
