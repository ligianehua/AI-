"""LLMClient 单测：mock 供应商，真 PG 验证记账（llm_calls）。"""

from decimal import Decimal
from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient
from app.ai.config import AIConfig
from app.ai.router import resolve
from app.core.config import get_settings
from app.core.exceptions import (
    LLMOutputError,
    LLMQuotaExceededError,
    LLMUnavailableError,
)
from app.models.llm_call import LlmCall
from tests.conftest import RoleUsers
from tests.fake_llm import (
    FakeOpenAI,
    FakeStream,
    completion,
    embedding_response,
    stream_chunk,
)

REQ = httpx.Request("POST", "https://fake.test/v1/chat/completions")


async def _llm_call_rows(session: AsyncSession) -> list[LlmCall]:
    rows = await session.scalars(select(LlmCall).order_by(LlmCall.created_at.asc()))
    return list(rows)


USER_MSG = [{"role": "user", "content": "ping"}]


async def test_chat_ok_and_accounting(
    llm: LLMClient, fakes: dict[str, FakeOpenAI], session: AsyncSession
) -> None:
    fakes["deepseek"].chat.completions.responses = [
        completion("pong", tokens_in=200_000, tokens_out=50_000)
    ]
    result = await llm.chat("ping", USER_MSG)
    assert result.content == "pong"
    assert result.provider == "deepseek"

    rows = await _llm_call_rows(session)
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "ok"
    assert row.task_type == "ping"
    assert (row.tokens_in, row.tokens_out) == (200_000, 50_000)
    # (200000*1.0 + 50000*4.0) / 1e6 = 0.4 元
    assert row.cost_estimate == Decimal("0.4000")


async def test_fallback_on_server_error(
    llm: LLMClient, fakes: dict[str, FakeOpenAI], session: AsyncSession
) -> None:
    fakes["deepseek"].chat.completions.responses = [
        openai.InternalServerError("boom", response=httpx.Response(500, request=REQ), body=None)
    ]
    fakes["qwen"].chat.completions.responses = [completion("来自 qwen")]

    result = await llm.chat("ping", USER_MSG)
    assert result.provider == "qwen"
    assert result.content == "来自 qwen"

    rows = await _llm_call_rows(session)
    assert [(r.provider, r.status) for r in rows] == [("deepseek", "error"), ("qwen", "ok")]


async def test_fallback_on_timeout(
    llm: LLMClient, fakes: dict[str, FakeOpenAI], session: AsyncSession
) -> None:
    fakes["deepseek"].chat.completions.responses = [openai.APITimeoutError(request=REQ)]
    fakes["qwen"].chat.completions.responses = [completion("ok")]

    result = await llm.chat("ping", USER_MSG)
    assert result.provider == "qwen"

    rows = await _llm_call_rows(session)
    assert [(r.provider, r.status) for r in rows] == [("deepseek", "timeout"), ("qwen", "ok")]


async def test_both_providers_fail(
    llm: LLMClient, fakes: dict[str, FakeOpenAI], session: AsyncSession
) -> None:
    err = openai.InternalServerError("down", response=httpx.Response(503, request=REQ), body=None)
    fakes["deepseek"].chat.completions.responses = [err]
    fakes["qwen"].chat.completions.responses = [
        openai.APIConnectionError(message="net down", request=REQ)
    ]

    with pytest.raises(LLMUnavailableError):
        await llm.chat("ping", USER_MSG)

    rows = await _llm_call_rows(session)
    assert len(rows) == 2
    assert all(r.status in ("error", "timeout") for r in rows)


async def test_non_retryable_error_no_fallback(
    llm: LLMClient, fakes: dict[str, FakeOpenAI], session: AsyncSession
) -> None:
    fakes["deepseek"].chat.completions.responses = [
        openai.BadRequestError("bad prompt", response=httpx.Response(400, request=REQ), body=None)
    ]
    with pytest.raises(LLMUnavailableError):
        await llm.chat("ping", USER_MSG)

    assert fakes["qwen"].chat.completions.calls == []  # 4xx 不降级
    rows = await _llm_call_rows(session)
    assert len(rows) == 1
    assert rows[0].status == "error"


class ScoreOut(BaseModel):
    score: int
    reason: str


async def test_structured_output_retry_once(
    llm: LLMClient, fakes: dict[str, FakeOpenAI], session: AsyncSession
) -> None:
    fakes["deepseek"].chat.completions.responses = [
        completion("这不是 JSON"),
        completion('{"score": 88, "reason": "预算明确"}'),
    ]
    out = await llm.chat_structured("lead_scoring", USER_MSG, ScoreOut)
    assert out.score == 88

    calls = fakes["deepseek"].chat.completions.calls
    assert len(calls) == 2
    assert calls[0]["response_format"] == {"type": "json_object"}
    retry_msgs = calls[1]["messages"]
    assert any("未通过格式校验" in m["content"] for m in retry_msgs if m["role"] == "user")

    rows = await _llm_call_rows(session)
    assert [r.status for r in rows] == ["ok", "ok"]


async def test_structured_output_fails_after_retry(
    llm: LLMClient, fakes: dict[str, FakeOpenAI]
) -> None:
    fakes["deepseek"].chat.completions.responses = [
        completion("还是不是 JSON"),
        completion("依旧不是 JSON"),
    ]
    with pytest.raises(LLMOutputError):
        await llm.chat_structured("lead_scoring", USER_MSG, ScoreOut)


async def test_daily_quota_exceeded(
    llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
    session: AsyncSession,
    roles: RoleUsers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "llm_daily_token_limit_per_user", 100)
    session.add(
        LlmCall(
            user_id=roles.sales_a.id,
            task_type="ping",
            provider="deepseek",
            model="deepseek-v4-flash",
            tokens_in=90,
            tokens_out=20,
            latency_ms=1,
            status="ok",
        )
    )
    await session.commit()

    with pytest.raises(LLMQuotaExceededError):
        await llm.chat("ping", USER_MSG, user_id=roles.sales_a.id)
    assert fakes["deepseek"].chat.completions.calls == []  # 未发起真实调用


async def test_chat_stream_and_accounting(
    llm: LLMClient, fakes: dict[str, FakeOpenAI], session: AsyncSession
) -> None:
    fakes["deepseek"].chat.completions.responses = [
        FakeStream(
            [
                stream_chunk("你好"),
                stream_chunk("，世界"),
                stream_chunk(usage=SimpleNamespace(prompt_tokens=12, completion_tokens=8)),
            ]
        )
    ]
    pieces = [piece async for piece in llm.chat_stream("script_gen", USER_MSG)]
    assert "".join(pieces) == "你好，世界"

    rows = await _llm_call_rows(session)
    assert len(rows) == 1
    assert rows[0].status == "ok"
    assert (rows[0].tokens_in, rows[0].tokens_out) == (12, 8)
    assert rows[0].task_type == "script_gen"


async def test_embed_routes_to_provider_with_embedding_tier(
    llm: LLMClient, fakes: dict[str, FakeOpenAI], session: AsyncSession
) -> None:
    fakes["qwen"].embeddings.responses = [embedding_response([[0.1] * 4, [0.2] * 4])]
    vectors = await llm.embed(["文本一", "文本二"])
    assert len(vectors) == 2

    rows = await _llm_call_rows(session)
    assert len(rows) == 1
    assert rows[0].provider == "qwen"  # deepseek 无 embedding 档位，自动落到 qwen
    assert rows[0].task_type == "embedding"


async def test_embed_splits_batches_over_limit(
    llm: LLMClient, fakes: dict[str, FakeOpenAI], session: AsyncSession
) -> None:
    """DashScope 系单请求最多 10 条：12 条应拆成 10+2 两次请求，结果顺序拼接。"""
    fakes["qwen"].embeddings.responses = [
        embedding_response([[float(i)] * 4 for i in range(10)], tokens_in=30),
        embedding_response([[10.0] * 4, [11.0] * 4], tokens_in=6),
    ]
    vectors = await llm.embed([f"文本{i}" for i in range(12)])
    assert len(vectors) == 12
    assert vectors[0] == [0.0] * 4
    assert vectors[11] == [11.0] * 4
    assert [len(c["input"]) for c in fakes["qwen"].embeddings.calls] == [10, 2]

    rows = await _llm_call_rows(session)
    assert len(rows) == 1  # 一次 embed() 记一行账，token 合计
    assert rows[0].tokens_in == 36


async def test_embed_retries_transient_failure_once(
    llm: LLMClient, fakes: dict[str, FakeOpenAI], session: AsyncSession
) -> None:
    """嵌入无降级路：5xx 等瞬时错误原地重试一次；重试成功不影响结果。"""
    err = openai.InternalServerError("boom", response=httpx.Response(500, request=REQ), body=None)
    fakes["qwen"].embeddings.responses = [err, embedding_response([[0.1] * 4])]
    vectors = await llm.embed(["文本"])
    assert len(vectors) == 1
    assert len(fakes["qwen"].embeddings.calls) == 2

    rows = await _llm_call_rows(session)
    assert [r.status for r in rows] == ["ok"]


def test_switch_provider_only_needs_config_change() -> None:
    """DoD：切换 provider 只改配置，代码零改动。"""
    base = {
        "providers": {
            "deepseek": {
                "base_url": "https://a",
                "api_key_env": "K1",
                "models": {"fast": "ds-fast"},
            },
            "qwen": {
                "base_url": "https://b",
                "api_key_env": "K2",
                "models": {"fast": "qw-fast"},
            },
        },
        "routing": {"ping": {"tier": "fast"}},
        "default_provider": "deepseek",
        "fallback_provider": "qwen",
    }
    cfg1 = AIConfig.model_validate(base)
    route1 = resolve("ping", cfg=cfg1)
    assert route1 is not None and route1.model == "ds-fast"

    cfg2 = AIConfig.model_validate({**base, "default_provider": "qwen"})
    route2 = resolve("ping", cfg=cfg2)
    assert route2 is not None and route2.model == "qw-fast"

    fb = resolve("ping", use_fallback=True, cfg=cfg1)
    assert fb is not None and fb.provider_name == "qwen"
