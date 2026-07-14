"""M9 通用 AI 助手：function calling 工具循环 + SSE 对话流。

- 4 个只读工具全部走 service 层 base_query（RBAC 天然继承当前用户）
- 工具循环上限 MAX_TOOL_ROUNDS 轮；未知工具/参数错误回填给 LLM 而非 500
- SSE 事件：tool {name, label} → delta {text} → done {llm_call_id} → error {message}
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import rag
from app.ai.client import LLMClient, Message, get_llm_client
from app.ai.prompt_loader import render_prompt
from app.core.exceptions import DomainError
from app.core.timezone import biz_today
from app.models.account import Account
from app.models.activity import Activity
from app.models.contact import Contact
from app.models.enums import (
    ActivityRelatedType,
    LeadStatus,
    LlmTaskType,
    OpportunityStage,
    Role,
    ScriptCategory,
)
from app.models.lead import Lead
from app.models.opportunity import Opportunity
from app.models.user import User
from app.schemas.assistant import ChatRequest
from app.services.account_service import account_service
from app.services.lead_service import lead_service
from app.services.opportunity_service import opportunity_service
from app.services.script_recommend import sse_event

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
MAX_TOOL_OUTPUT_CHARS = 6000  # 单个工具结果注入上限（防 token 爆炸）

ROLE_LABELS = {Role.SALES: "销售", Role.MANAGER: "主管", Role.ADMIN: "管理员"}

OPEN_STAGES = (
    OpportunityStage.INITIAL,
    OpportunityStage.NEED_CONFIRMED,
    OpportunityStage.PROPOSAL,
    OpportunityStage.NEGOTIATION,
)

TOOL_LABELS = {
    "search_leads": "正在查询线索…",
    "search_opportunities": "正在查询商机…",
    "get_account_360": "正在查看客户档案…",
    "recommend_scripts": "正在检索话术库…",
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_leads",
            "description": "查询当前用户可见的销售线索列表（含 AI 评分、状态、来源），按评分降序。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": [s.value for s in LeadStatus],
                        "description": (
                            "按状态筛选：new 新线索 / contacted 已联系 / qualified 已确认"
                            " / converted 已转化 / invalid 无效"
                        ),
                    },
                    "min_score": {"type": "integer", "description": "最低 AI 评分（0-100）"},
                    "keyword": {"type": "string", "description": "公司名关键词（模糊匹配）"},
                    "limit": {"type": "integer", "description": "返回条数，默认 10，最多 20"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_opportunities",
            "description": (
                "查询当前用户可见的商机列表（含金额、阶段、阶段停留天数、距上次跟进天数）。"
                "判断商机风险/停滞/失联时用这个工具。不传 stage 时只查进行中的商机。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stage": {
                        "type": "string",
                        "enum": [s.value for s in OpportunityStage],
                        "description": "按阶段筛选；won 已赢单 / lost 已丢单；不传则查全部进行中",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "商机名或客户名关键词（模糊匹配）",
                    },
                    "limit": {"type": "integer", "description": "返回条数，默认 10，最多 20"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_account_360",
            "description": "按客户名查客户 360：基本信息、AI 画像摘要、联系人、最近 5 条跟进记录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_name": {"type": "string", "description": "客户公司名（支持模糊匹配）"}
                },
                "required": ["account_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_scripts",
            "description": "按场景/问题在话术库做混合检索，返回最相关的 5 条话术原文。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "场景描述，如：客户嫌贵怎么回应"},
                    "category": {
                        "type": "string",
                        "enum": [c.value for c in ScriptCategory],
                        "description": (
                            "话术分类（可选）：opening 开场 / discovery 挖需 / objection 异议"
                            " / pricing 价格 / closing 成交 / retention 维系"
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
]


# ---------- 工具参数 schema（LLM 产出的参数必须过校验，坏参数回填错误） ----------


class _SearchLeadsArgs(BaseModel):
    status: LeadStatus | None = None
    min_score: int | None = Field(None, ge=0, le=100)
    keyword: str | None = Field(None, max_length=100)
    limit: int = Field(10, ge=1, le=20)


class _SearchOppsArgs(BaseModel):
    stage: OpportunityStage | None = None
    keyword: str | None = Field(None, max_length=100)
    limit: int = Field(10, ge=1, le=20)


class _Account360Args(BaseModel):
    account_name: str = Field(min_length=1, max_length=200)


class _RecommendScriptsArgs(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    category: ScriptCategory | None = None


def _days_since(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    aware = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return max(0, (datetime.now(UTC) - aware).days)


async def _tool_search_leads(session: AsyncSession, actor: User, raw: dict[str, Any]) -> Any:
    args = _SearchLeadsArgs.model_validate(raw)
    stmt = lead_service.base_query(actor)
    if args.status is not None:
        stmt = stmt.where(Lead.status == args.status)
    if args.min_score is not None:
        stmt = stmt.where(Lead.score >= args.min_score)
    if args.keyword:
        stmt = stmt.where(Lead.account_name.ilike(f"%{args.keyword}%"))
    rows = (
        await session.execute(
            stmt.add_columns(User.name)
            .join(User, User.id == Lead.owner_id)
            .order_by(Lead.score.desc().nulls_last())
            .limit(args.limit)
        )
    ).all()
    return [
        {
            "客户公司": lead.account_name,
            "状态": lead.status,
            "评分": lead.score,
            "来源": lead.source,
            "联系人": lead.contact_name,
            "负责人": owner_name,
            "创建日期": lead.created_at.date().isoformat(),
        }
        for lead, owner_name in rows
    ]


async def _tool_search_opportunities(
    session: AsyncSession, actor: User, raw: dict[str, Any]
) -> Any:
    args = _SearchOppsArgs.model_validate(raw)
    stmt = (
        opportunity_service.base_query(actor)
        .add_columns(Account.name, User.name)
        .join(Account, Account.id == Opportunity.account_id)
        .join(User, User.id == Opportunity.owner_id)
    )
    if args.stage is not None:
        stmt = stmt.where(Opportunity.stage == args.stage)
    else:
        stmt = stmt.where(Opportunity.stage.in_([s.value for s in OPEN_STAGES]))
    if args.keyword:
        kw = f"%{args.keyword}%"
        stmt = stmt.where(Opportunity.name.ilike(kw) | Account.name.ilike(kw))
    rows = (await session.execute(stmt.order_by(Opportunity.amount.desc()).limit(args.limit))).all()

    opp_ids = [opp.id for opp, _, _ in rows]
    last_activity: dict[uuid.UUID, datetime] = {}
    if opp_ids:
        for related_id, latest in (
            await session.execute(
                select(Activity.related_id, func.max(Activity.created_at))
                .where(
                    Activity.related_type == ActivityRelatedType.OPPORTUNITY,
                    Activity.related_id.in_(opp_ids),
                    Activity.deleted_at.is_(None),
                )
                .group_by(Activity.related_id)
            )
        ).all():
            last_activity[related_id] = latest

    result = []
    for opp, account_name, owner_name in rows:
        stage_entered: datetime | None = None
        if opp.stage_history:
            with_entered = opp.stage_history[-1].get("entered_at")
            if with_entered:
                stage_entered = datetime.fromisoformat(with_entered)
        followup_base = last_activity.get(opp.id) or opp.created_at
        result.append(
            {
                "商机": opp.name,
                "客户": account_name,
                "金额元": float(opp.amount),
                "阶段": opp.stage,
                "赢单概率": opp.probability,
                "预计成交日": (
                    opp.expected_close_date.isoformat() if opp.expected_close_date else None
                ),
                "距上次跟进天数": _days_since(followup_base),
                "阶段停留天数": _days_since(stage_entered or opp.created_at),
                "负责人": owner_name,
            }
        )
    return result


async def _tool_get_account_360(session: AsyncSession, actor: User, raw: dict[str, Any]) -> Any:
    args = _Account360Args.model_validate(raw)
    account = await session.scalar(
        account_service.base_query(actor)
        .where(Account.name.ilike(f"%{args.account_name}%"))
        .order_by(Account.created_at.desc())
        .limit(1)
    )
    if account is None:
        return {"error": f"没有查到客户「{args.account_name}」（可能不存在或不在你的可见范围内）"}

    contacts = list(
        await session.scalars(
            select(Contact).where(Contact.account_id == account.id, Contact.deleted_at.is_(None))
        )
    )
    opp_ids = list(
        await session.scalars(
            select(Opportunity.id).where(
                Opportunity.account_id == account.id, Opportunity.deleted_at.is_(None)
            )
        )
    )
    related_filter = (Activity.related_type == ActivityRelatedType.ACCOUNT) & (
        Activity.related_id == account.id
    )
    if opp_ids:
        related_filter = related_filter | (
            (Activity.related_type == ActivityRelatedType.OPPORTUNITY)
            & Activity.related_id.in_(opp_ids)
        )
    activities = list(
        await session.scalars(
            select(Activity)
            .where(related_filter, Activity.deleted_at.is_(None))
            .order_by(Activity.created_at.desc())
            .limit(5)
        )
    )

    profile = account.ai_profile or {}
    return {
        "客户": account.name,
        "行业": account.industry,
        "规模": account.size,
        "地区": account.region,
        "AI画像": {
            "公司概况": profile.get("company_overview"),
            "痛点": profile.get("pain_points"),
            "风险": profile.get("risks"),
            "建议": profile.get("suggestions"),
        }
        if profile
        else "（尚未生成画像）",
        "联系人": [
            {"姓名": c.name, "职位": c.title, "角色": c.role_in_deal, "电话": c.phone}
            for c in contacts
        ],
        "最近跟进": [
            {
                "日期": a.created_at.date().isoformat(),
                "方式": a.type,
                "内容": a.content[:200],
                "下一步": a.next_action,
            }
            for a in activities
        ],
    }


async def _tool_recommend_scripts(session: AsyncSession, actor: User, raw: dict[str, Any]) -> Any:
    args = _RecommendScriptsArgs.model_validate(raw)
    hits = await rag.search_scripts(
        session,
        args.query,
        category=args.category.value if args.category else None,
        top_k=5,
        user_id=actor.id,
    )
    if not hits:
        return {"error": "话术库中没有匹配的话术"}
    return [{"场景": h.script.scenario, "话术": h.script.content} for h in hits]


_TOOL_HANDLERS = {
    "search_leads": _tool_search_leads,
    "search_opportunities": _tool_search_opportunities,
    "get_account_360": _tool_get_account_360,
    "recommend_scripts": _tool_recommend_scripts,
}


async def execute_tool(session: AsyncSession, actor: User, name: str, arguments: str) -> str:
    """执行一次工具调用。任何失败都转成给 LLM 的错误说明，绝不向上抛。"""
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        return json.dumps({"error": f"未知工具：{name}"}, ensure_ascii=False)
    try:
        raw = json.loads(arguments or "{}")
        if not isinstance(raw, dict):
            raise ValueError("参数必须是 JSON 对象")
        result = await handler(session, actor, raw)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        return json.dumps({"error": f"参数不合法：{exc}"}, ensure_ascii=False)
    except Exception:
        logger.exception("助手工具执行失败：%s(%s)", name, arguments[:200])
        return json.dumps({"error": "工具执行失败，请换个问法或稍后重试"}, ensure_ascii=False)
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > MAX_TOOL_OUTPUT_CHARS:
        text = text[:MAX_TOOL_OUTPUT_CHARS] + "…（结果过长已截断）"
    return text


def _system_prompt(actor: User) -> str:
    return render_prompt(
        "assistant_chat.j2",
        user_name=actor.name,
        role_label=ROLE_LABELS.get(Role(actor.role), actor.role),
        today=biz_today().isoformat(),
    )


async def chat_stream_events(
    session: AsyncSession,
    actor: User,
    payload: ChatRequest,
    llm: LLMClient | None = None,
) -> AsyncIterator[str]:
    """助手对话 SSE 流：工具循环 → 最终回答流式输出。"""
    llm = llm or get_llm_client()
    messages: list[Message] = [
        {"role": "system", "content": _system_prompt(actor)},
        *[{"role": h.role, "content": h.content} for h in payload.history[-10:]],
        {"role": "user", "content": payload.message},
    ]
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            result = await llm.chat_tools(LlmTaskType.CHAT, messages, TOOLS, user_id=actor.id)
            if not result.tool_calls:
                # 模型直接作答（闲聊/拒答等短路径），内容已完整
                if result.content:
                    yield sse_event("delta", {"text": result.content})
                    yield sse_event("done", {"llm_call_id": None})
                    return
                break  # 空回复 → 落到下方强制作答
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
                output = await execute_tool(session, actor, call.name, call.arguments)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": output})

        # 工具轮次用尽（或模型空回复）：带上下文强制输出最终回答（流式）
        meta: dict[str, Any] = {}
        async for piece in llm.chat_stream(
            LlmTaskType.CHAT,
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
        logger.exception("助手对话失败")
        yield sse_event("error", {"message": "助手暂时不可用，请稍后重试"})
