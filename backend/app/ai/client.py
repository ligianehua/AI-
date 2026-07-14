"""LLM 统一客户端。

- 协议统一：openai SDK + base_url 覆盖（DeepSeek/Qwen/Kimi/GLM 均 OpenAI 兼容）
- 超时 60s；SDK 内置指数退避重试 2 次
- 主供应商 5xx/超时/连接失败/限流 → fallback 供应商降级重试一次（embedding 除外：
  换嵌入模型会导致向量空间不一致，宁可失败也不混库）
- 结构化输出：JSON mode + Pydantic 校验，失败附错误提示重试一次
- 每次供应商调用（含失败与降级的每一跳）写 llm_calls 记账；记账失败不阻断业务调用
- 成本护栏：每用户日 token 限额（settings.llm_daily_token_limit_per_user，0=不限）
- Anthropic 原生协议 adapter 接口预留（P0 不实现）
"""

import logging
import os
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any, cast

import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.config import ProviderConfig, get_ai_config
from app.ai.router import ResolvedRoute, resolve
from app.core.config import get_settings
from app.core.exceptions import (
    LLMOutputError,
    LLMQuotaExceededError,
    LLMUnavailableError,
)
from app.core.timezone import biz_day_start_utc
from app.models.llm_call import LlmCall

logger = logging.getLogger(__name__)

# DashScope 系嵌入接口单请求批量上限
EMBED_BATCH_SIZE = 10

# 值放宽为 Any：tool 消息带 tool_call_id、assistant 消息带 tool_calls 列表
Message = dict[str, Any]
ClientFactory = Callable[[str, ProviderConfig], AsyncOpenAI]

_RETRY_PROMPT = (
    "你上一次的输出未通过格式校验，错误如下：\n{error}\n"
    "请重新输出，只输出一个符合要求的 JSON 对象，不要包含任何其他文字。"
)


@dataclass(frozen=True)
class ChatResult:
    content: str
    provider: str
    model: str
    latency_ms: int


@dataclass(frozen=True)
class ToolCallRequest:
    """LLM 发起的一次工具调用请求（arguments 为原始 JSON 字符串，由调用方解析校验）。"""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolsResult:
    """带工具的补全结果：tool_calls 非空表示 LLM 要求执行工具，否则 content 即答案。"""

    content: str
    tool_calls: list[ToolCallRequest]
    provider: str
    model: str
    latency_ms: int


def _default_client_factory(provider_name: str, provider: ProviderConfig) -> AsyncOpenAI:
    api_key = os.environ.get(provider.api_key_env)
    if not api_key:
        raise LLMUnavailableError(
            f"供应商 {provider_name} 未配置密钥（.env 缺 {provider.api_key_env}）"
        )
    return AsyncOpenAI(base_url=provider.base_url, api_key=api_key, timeout=60.0, max_retries=2)


def _failure_status(exc: Exception) -> str | None:
    """可降级错误 → llm_calls.status；不可降级返回 None。"""
    if isinstance(exc, openai.APITimeoutError):
        return "timeout"
    if isinstance(exc, openai.APIConnectionError):
        return "error"
    if isinstance(exc, openai.RateLimitError):
        return "error"
    if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
        return "error"
    if isinstance(exc, LLMUnavailableError):  # 如密钥缺失，可尝试降级
        return "error"
    return None


class LLMClient:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession] | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._sessionmaker_override = sessionmaker
        self._client_factory = client_factory or _default_client_factory
        self._clients: dict[str, AsyncOpenAI] = {}

    # ---------- 基础设施 ----------

    def _sessionmaker(self) -> async_sessionmaker[AsyncSession]:
        if self._sessionmaker_override is not None:
            return self._sessionmaker_override
        from app.core.db import get_sessionmaker

        return get_sessionmaker()

    def _client_for(self, route: ResolvedRoute) -> AsyncOpenAI:
        if route.provider_name not in self._clients:
            self._clients[route.provider_name] = self._client_factory(
                route.provider_name, route.provider
            )
        return self._clients[route.provider_name]

    def _estimate_cost(self, model: str, tokens_in: int, tokens_out: int) -> Decimal:
        price = get_ai_config().pricing.get(model)
        if price is None:
            return Decimal(0)
        return (Decimal(tokens_in) * price.input + Decimal(tokens_out) * price.output) / Decimal(
            1_000_000
        )

    async def _record(
        self,
        *,
        user_id: uuid.UUID | None,
        task_type: str,
        provider: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: int,
        status: str,
        error_msg: str | None = None,
    ) -> uuid.UUID | None:
        """写 llm_calls 记账，返回记录 id（用户反馈的落点）；记账失败只记日志，不阻断业务调用。"""
        try:
            async with self._sessionmaker()() as session:
                call = LlmCall(
                    user_id=user_id,
                    task_type=task_type,
                    provider=provider,
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_estimate=self._estimate_cost(model, tokens_in, tokens_out),
                    latency_ms=latency_ms,
                    status=status,
                    error_msg=error_msg[:500] if error_msg else None,
                )
                session.add(call)
                await session.commit()
                return call.id
        except Exception:
            logger.exception("llm_calls 记账失败（task_type=%s provider=%s）", task_type, provider)
            return None

    async def _check_quota(self, user_id: uuid.UUID | None) -> None:
        limit = get_settings().llm_daily_token_limit_per_user
        if not limit or user_id is None:
            return
        today_start = biz_day_start_utc()  # 日限额按 Asia/Shanghai 日界
        async with self._sessionmaker()() as session:
            used = await session.scalar(
                select(func.coalesce(func.sum(LlmCall.tokens_in + LlmCall.tokens_out), 0)).where(
                    LlmCall.user_id == user_id, LlmCall.created_at >= today_start
                )
            )
        if int(used or 0) >= limit:
            raise LLMQuotaExceededError(f"已达到今日 AI 用量上限（{limit} tokens），请明天再试")

    # ---------- 单次调用 ----------

    async def _complete_once(
        self,
        route: ResolvedRoute,
        messages: list[Message],
        *,
        task_type: str,
        user_id: uuid.UUID | None,
        json_mode: bool,
    ) -> ChatResult:
        started = time.perf_counter()
        try:
            client = self._client_for(route)
            kwargs: dict[str, Any] = {}
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = await client.chat.completions.create(
                model=route.model,
                messages=cast(list[ChatCompletionMessageParam], messages),
                temperature=route.temperature,
                **kwargs,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            await self._record(
                user_id=user_id,
                task_type=task_type,
                provider=route.provider_name,
                model=route.model,
                tokens_in=0,
                tokens_out=0,
                latency_ms=latency_ms,
                status=_failure_status(exc) or "error",
                error_msg=str(exc),
            )
            raise
        latency_ms = int((time.perf_counter() - started) * 1000)
        tokens_in = resp.usage.prompt_tokens if resp.usage else 0
        tokens_out = resp.usage.completion_tokens if resp.usage else 0
        await self._record(
            user_id=user_id,
            task_type=task_type,
            provider=route.provider_name,
            model=route.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            status="ok",
        )
        content = resp.choices[0].message.content or ""
        return ChatResult(
            content=content,
            provider=route.provider_name,
            model=route.model,
            latency_ms=latency_ms,
        )

    async def _complete_with_fallback(
        self,
        task_type: str,
        messages: list[Message],
        *,
        user_id: uuid.UUID | None,
        json_mode: bool | None = None,
    ) -> ChatResult:
        await self._check_quota(user_id)
        route = resolve(task_type)
        assert route is not None
        effective_json = route.json_mode if json_mode is None else json_mode
        try:
            return await self._complete_once(
                route, messages, task_type=task_type, user_id=user_id, json_mode=effective_json
            )
        except Exception as exc:
            if _failure_status(exc) is None:
                raise LLMUnavailableError("AI 服务暂不可用，请稍后再试") from exc
            fallback = resolve(task_type, use_fallback=True)
            if fallback is None:
                raise LLMUnavailableError("AI 服务暂不可用，请稍后再试") from exc
            logger.warning(
                "供应商 %s 调用失败（%s），降级到 %s",
                route.provider_name,
                exc,
                fallback.provider_name,
            )
            try:
                return await self._complete_once(
                    fallback,
                    messages,
                    task_type=task_type,
                    user_id=user_id,
                    json_mode=effective_json,
                )
            except Exception as exc2:
                raise LLMUnavailableError("AI 服务暂不可用，请稍后再试") from exc2

    # ---------- 对外接口 ----------

    async def chat(
        self, task_type: str, messages: list[Message], *, user_id: uuid.UUID | None = None
    ) -> ChatResult:
        """非流式文本补全（json 路由配置生效）。"""
        return await self._complete_with_fallback(task_type, messages, user_id=user_id)

    async def chat_structured[S: BaseModel](
        self,
        task_type: str,
        messages: list[Message],
        output_schema: type[S],
        *,
        user_id: uuid.UUID | None = None,
    ) -> S:
        """结构化输出：JSON mode + Pydantic 校验，校验失败附错误提示重试一次。"""
        result = await self._complete_with_fallback(
            task_type, messages, user_id=user_id, json_mode=True
        )
        try:
            return output_schema.model_validate_json(result.content)
        except ValidationError as err:
            retry_messages = [
                *messages,
                {"role": "assistant", "content": result.content},
                {"role": "user", "content": _RETRY_PROMPT.format(error=str(err)[:1000])},
            ]
            retry = await self._complete_with_fallback(
                task_type, retry_messages, user_id=user_id, json_mode=True
            )
            try:
                return output_schema.model_validate_json(retry.content)
            except ValidationError as err2:
                raise LLMOutputError("AI 返回格式不合法，已重试仍失败") from err2

    async def chat_tools(
        self,
        task_type: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
        *,
        user_id: uuid.UUID | None = None,
    ) -> ToolsResult:
        """带工具的非流式补全（function calling 一轮）。降级策略与 chat 一致。"""
        await self._check_quota(user_id)
        route = resolve(task_type)
        assert route is not None
        try:
            return await self._complete_tools_once(
                route, messages, tools, task_type=task_type, user_id=user_id
            )
        except Exception as exc:
            if _failure_status(exc) is None:
                raise LLMUnavailableError("AI 服务暂不可用，请稍后再试") from exc
            fallback = resolve(task_type, use_fallback=True)
            if fallback is None:
                raise LLMUnavailableError("AI 服务暂不可用，请稍后再试") from exc
            logger.warning(
                "供应商 %s 工具调用失败（%s），降级到 %s",
                route.provider_name,
                exc,
                fallback.provider_name,
            )
            try:
                return await self._complete_tools_once(
                    fallback, messages, tools, task_type=task_type, user_id=user_id
                )
            except Exception as exc2:
                raise LLMUnavailableError("AI 服务暂不可用，请稍后再试") from exc2

    async def _complete_tools_once(
        self,
        route: ResolvedRoute,
        messages: list[Message],
        tools: list[dict[str, Any]],
        *,
        task_type: str,
        user_id: uuid.UUID | None,
    ) -> ToolsResult:
        started = time.perf_counter()
        try:
            client = self._client_for(route)
            resp = await client.chat.completions.create(
                model=route.model,
                messages=cast(list[ChatCompletionMessageParam], messages),
                temperature=route.temperature,
                tools=cast(Any, tools),
            )
        except Exception as exc:
            await self._record(
                user_id=user_id,
                task_type=task_type,
                provider=route.provider_name,
                model=route.model,
                tokens_in=0,
                tokens_out=0,
                latency_ms=int((time.perf_counter() - started) * 1000),
                status=_failure_status(exc) or "error",
                error_msg=str(exc),
            )
            raise
        latency_ms = int((time.perf_counter() - started) * 1000)
        await self._record(
            user_id=user_id,
            task_type=task_type,
            provider=route.provider_name,
            model=route.model,
            tokens_in=resp.usage.prompt_tokens if resp.usage else 0,
            tokens_out=resp.usage.completion_tokens if resp.usage else 0,
            latency_ms=latency_ms,
            status="ok",
        )
        msg = resp.choices[0].message
        calls: list[ToolCallRequest] = []
        for tc in msg.tool_calls or []:
            fn = getattr(tc, "function", None)  # 排除非 function 类型的自定义工具调用
            if fn is not None:
                calls.append(
                    ToolCallRequest(id=tc.id, name=fn.name, arguments=fn.arguments or "{}")
                )
        return ToolsResult(
            content=msg.content or "",
            tool_calls=calls,
            provider=route.provider_name,
            model=route.model,
            latency_ms=latency_ms,
        )

    async def chat_stream(
        self,
        task_type: str,
        messages: list[Message],
        *,
        user_id: uuid.UUID | None = None,
        meta: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
    ) -> AsyncIterator[str]:
        """流式补全。仅在建立连接阶段降级；流中途出错直接报错并记账。

        meta：调用方传入 dict 时，流成功结束后写入 meta["llm_call_id"]（用户反馈落点）。
        tools/tool_choice：消息里含 tool 角色时必须带上 tools（协议要求）；
        tool_choice="none" 强制模型只输出文本（助手最终作答用）。
        """
        await self._check_quota(user_id)
        route = resolve(task_type)
        assert route is not None
        started = time.perf_counter()

        async def _open(r: ResolvedRoute) -> Any:
            client = self._client_for(r)
            kwargs: dict[str, Any] = {}
            if tools is not None:
                kwargs["tools"] = tools
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice
            return await client.chat.completions.create(
                model=r.model,
                messages=cast(list[ChatCompletionMessageParam], messages),
                temperature=r.temperature,
                stream=True,
                stream_options={"include_usage": True},
                **kwargs,
            )

        try:
            stream = await _open(route)
        except Exception as exc:
            await self._record(
                user_id=user_id,
                task_type=task_type,
                provider=route.provider_name,
                model=route.model,
                tokens_in=0,
                tokens_out=0,
                latency_ms=int((time.perf_counter() - started) * 1000),
                status=_failure_status(exc) or "error",
                error_msg=str(exc),
            )
            if _failure_status(exc) is None:
                raise LLMUnavailableError("AI 服务暂不可用，请稍后再试") from exc
            fb = resolve(task_type, use_fallback=True)
            if fb is None:
                raise LLMUnavailableError("AI 服务暂不可用，请稍后再试") from exc
            logger.warning("流式调用降级：%s -> %s", route.provider_name, fb.provider_name)
            route = fb
            fb_started = time.perf_counter()
            try:
                stream = await _open(route)
            except Exception as exc2:
                await self._record(
                    user_id=user_id,
                    task_type=task_type,
                    provider=route.provider_name,
                    model=route.model,
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=int((time.perf_counter() - fb_started) * 1000),
                    status=_failure_status(exc2) or "error",
                    error_msg=str(exc2),
                )
                raise LLMUnavailableError("AI 服务暂不可用，请稍后再试") from exc2

        tokens_in = 0
        tokens_out = 0
        try:
            async for chunk in stream:
                if getattr(chunk, "usage", None):
                    tokens_in = chunk.usage.prompt_tokens
                    tokens_out = chunk.usage.completion_tokens
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            await self._record(
                user_id=user_id,
                task_type=task_type,
                provider=route.provider_name,
                model=route.model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=int((time.perf_counter() - started) * 1000),
                status="error",
                error_msg=str(exc),
            )
            raise LLMUnavailableError("AI 输出中断，请重试") from exc
        call_id = await self._record(
            user_id=user_id,
            task_type=task_type,
            provider=route.provider_name,
            model=route.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=int((time.perf_counter() - started) * 1000),
            status="ok",
        )
        if meta is not None and call_id is not None:
            meta["llm_call_id"] = str(call_id)

    async def embed(
        self, texts: list[str], *, user_id: uuid.UUID | None = None
    ) -> list[list[float]]:
        """文本嵌入。不做供应商降级：换嵌入模型会导致向量空间不一致。

        DashScope 系 text-embedding-v4 单请求最多 10 条，超出按批切分串行请求。
        """
        await self._check_quota(user_id)
        route = resolve("embedding")
        assert route is not None
        started = time.perf_counter()
        try:
            client = self._client_for(route)
            vectors: list[list[float]] = []
            tokens_in = 0
            for i in range(0, len(texts), EMBED_BATCH_SIZE):
                batch = texts[i : i + EMBED_BATCH_SIZE]
                try:
                    resp = await client.embeddings.create(model=route.model, input=batch)
                except Exception as exc:
                    # 嵌入无降级路（向量空间一致性），瞬时错误原地重试一次；
                    # 密钥缺失等确定性错误直接抛出
                    if _failure_status(exc) is None or isinstance(exc, LLMUnavailableError):
                        raise
                    logger.warning("嵌入请求瞬时失败（%s），重试一次", exc)
                    resp = await client.embeddings.create(model=route.model, input=batch)
                vectors.extend(item.embedding for item in resp.data)
                if resp.usage:
                    tokens_in += resp.usage.prompt_tokens
        except Exception as exc:
            await self._record(
                user_id=user_id,
                task_type="embedding",
                provider=route.provider_name,
                model=route.model,
                tokens_in=0,
                tokens_out=0,
                latency_ms=int((time.perf_counter() - started) * 1000),
                status=_failure_status(exc) or "error",
                error_msg=str(exc),
            )
            if isinstance(exc, LLMUnavailableError):
                raise
            raise LLMUnavailableError("嵌入服务暂不可用，请稍后再试") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        await self._record(
            user_id=user_id,
            task_type="embedding",
            provider=route.provider_name,
            model=route.model,
            tokens_in=tokens_in,
            tokens_out=0,
            latency_ms=latency_ms,
            status="ok",
        )
        return vectors


@lru_cache
def get_llm_client() -> LLMClient:
    """应用级单例（FastAPI 依赖用；测试用 dependency_overrides 替换）。"""
    return LLMClient()
