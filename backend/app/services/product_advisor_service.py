"""M14 产品咨询助手：双角色对话（售前专家/售后运维），复用 chat_tools 循环框架。

安全红线：售后排查步骤必须来自知识库检索，查不到就转人工（prompt 铁律 + 工具只读）。
SSE 协议与 M9 助手一致：tool → delta* → done → error。
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import rag
from app.ai.client import LLMClient, Message, get_llm_client
from app.ai.prompt_loader import render_prompt
from app.core.exceptions import DomainError
from app.core.timezone import biz_today
from app.models.enums import LlmTaskType
from app.models.product import Product
from app.models.user import User
from app.schemas.assistant import ChatRequest
from app.services import product_service
from app.services.script_recommend import sse_event

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
MAX_TOOL_OUTPUT_CHARS = 6000

TOOL_LABELS = {
    "search_products": "正在检索产品库…",
    "get_product_detail": "正在调取产品参数…",
    "compare_products": "正在生成参数对比…",
    "search_knowledge": "正在查阅知识库/运维手册…",
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "按需求描述/参数条件在产品库检索候选产品（售前选型第一步）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "需求描述，如：380V 小功率变频器"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 5，最多 10"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_detail",
            "description": "按型号取产品完整参数（回答具体参数/能力问题时用）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_no": {"type": "string", "description": "产品型号（支持模糊匹配）"}
                },
                "required": ["model_no"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_products",
            "description": "对 2-4 个型号生成参数对齐矩阵（对比/卖点提炼时用）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "model_nos": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "2-4 个产品型号",
                    }
                },
                "required": ["model_nos"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "在知识库（FAQ/运维手册/案例）中检索。售后问题（故障/报错/维护/操作）"
                "必须先查这里——排查步骤只能来自检索结果。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "问题描述，如：E03 报错怎么处理"}
                },
                "required": ["query"],
            },
        },
    },
]


class _SearchArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(5, ge=1, le=10)


class _DetailArgs(BaseModel):
    model_no: str = Field(min_length=1, max_length=100)


class _CompareArgs(BaseModel):
    model_nos: list[str] = Field(min_length=2, max_length=4)


class _KnowledgeArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)


def _product_brief(p: Product, max_specs: int = 6) -> dict[str, Any]:
    specs = dict(list(p.specs.items())[:max_specs])
    return {
        "型号": p.model_no,
        "名称": p.name,
        "品牌": p.brand,
        "品类": p.category,
        "状态": "停产" if p.status == "eol" else "在售",
        "关键参数": specs,
    }


async def _tool_search_products(
    session: AsyncSession, actor: User, raw: dict[str, Any], llm: LLMClient
) -> Any:
    args = _SearchArgs.model_validate(raw)
    hits = await product_service.search_products(
        session, args.query, top_k=args.top_k, llm=llm, user_id=actor.id
    )
    if not hits:
        return {"error": "产品库中没有匹配的产品"}
    return [_product_brief(p) for p, _ in hits]


async def _tool_get_product_detail(
    session: AsyncSession, actor: User, raw: dict[str, Any], llm: LLMClient
) -> Any:
    args = _DetailArgs.model_validate(raw)
    product = await session.scalar(
        select(Product)
        .where(Product.model_no.ilike(f"%{args.model_no}%"), Product.deleted_at.is_(None))
        .limit(1)
    )
    if product is None:
        return {"error": f"没有找到型号「{args.model_no}」的产品"}
    return {
        "型号": product.model_no,
        "名称": product.name,
        "品牌": product.brand,
        "品类": product.category,
        "状态": "停产" if product.status == "eol" else "在售",
        "全部参数": product.specs,
        "描述": product.description,
    }


async def _tool_compare_products(
    session: AsyncSession, actor: User, raw: dict[str, Any], llm: LLMClient
) -> Any:
    args = _CompareArgs.model_validate(raw)
    products: list[Product] = []
    missing: list[str] = []
    for model_no in args.model_nos:
        product = await session.scalar(
            select(Product)
            .where(Product.model_no.ilike(f"%{model_no}%"), Product.deleted_at.is_(None))
            .limit(1)
        )
        if product is None:
            missing.append(model_no)
        else:
            products.append(product)
    if len(products) < 2:
        return {"error": f"可对比产品不足 2 个（未找到：{'、'.join(missing) or '—'}）"}
    matrix = product_service.build_compare_matrix(products)
    if missing:
        matrix["missing"] = missing
    return matrix


async def _tool_search_knowledge(
    session: AsyncSession, actor: User, raw: dict[str, Any], llm: LLMClient
) -> Any:
    args = _KnowledgeArgs.model_validate(raw)
    hits = await rag.search_knowledge(session, args.query, top_k=3, llm=llm, user_id=actor.id)
    if not hits:
        return {"error": "知识库中没有相关内容——请按铁律回复：无法提供排查步骤，建议转人工工程师"}
    return [{"文档": h.doc_title, "内容": h.chunk.content} for h in hits]


_TOOL_HANDLERS = {
    "search_products": _tool_search_products,
    "get_product_detail": _tool_get_product_detail,
    "compare_products": _tool_compare_products,
    "search_knowledge": _tool_search_knowledge,
}


async def execute_tool(
    session: AsyncSession, actor: User, name: str, arguments: str, llm: LLMClient
) -> str:
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        return json.dumps({"error": f"未知工具：{name}"}, ensure_ascii=False)
    try:
        raw = json.loads(arguments or "{}")
        if not isinstance(raw, dict):
            raise ValueError("参数必须是 JSON 对象")
        result = await handler(session, actor, raw, llm)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        return json.dumps({"error": f"参数不合法：{exc}"}, ensure_ascii=False)
    except Exception:
        logger.exception("咨询工具执行失败：%s(%s)", name, arguments[:200])
        return json.dumps({"error": "工具执行失败，请换个问法或稍后重试"}, ensure_ascii=False)
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > MAX_TOOL_OUTPUT_CHARS:
        text = text[:MAX_TOOL_OUTPUT_CHARS] + "…（结果过长已截断）"
    return text


async def chat_stream_events(
    session: AsyncSession,
    actor: User,
    payload: ChatRequest,
    llm: LLMClient | None = None,
) -> AsyncIterator[str]:
    llm = llm or get_llm_client()
    messages: list[Message] = [
        {
            "role": "system",
            "content": render_prompt(
                "product_advisor.j2", user_name=actor.name, today=biz_today().isoformat()
            ),
        },
        *[{"role": h.role, "content": h.content} for h in payload.history[-10:]],
        {"role": "user", "content": payload.message},
    ]
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            result = await llm.chat_tools(
                LlmTaskType.PRODUCT_ADVISOR, messages, TOOLS, user_id=actor.id
            )
            if not result.tool_calls:
                if result.content:
                    yield sse_event("delta", {"text": result.content})
                    yield sse_event("done", {"llm_call_id": None})
                    return
                break
            messages.append(
                {
                    "role": "assistant",
                    "content": result.content or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": c.arguments},
                        }
                        for c in result.tool_calls
                    ],
                }
            )
            for call in result.tool_calls:
                yield sse_event(
                    "tool", {"name": call.name, "label": TOOL_LABELS.get(call.name, "正在查询…")}
                )
                output = await execute_tool(session, actor, call.name, call.arguments, llm)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": output})

        meta: dict[str, Any] = {}
        async for piece in llm.chat_stream(
            LlmTaskType.PRODUCT_ADVISOR,
            messages,
            user_id=actor.id,
            meta=meta,
            tools=TOOLS,
            tool_choice="none",
        ):
            yield sse_event("delta", {"text": piece})
        yield sse_event("done", {"llm_call_id": meta.get("llm_call_id")})
    except DomainError as exc:
        yield sse_event("error", {"message": exc.message})
    except Exception:
        logger.exception("产品咨询对话失败")
        yield sse_event("error", {"message": "咨询助手暂时不可用，请稍后重试"})
