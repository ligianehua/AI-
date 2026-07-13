"""话术推荐生成管线（SSE）。

检索(scripts top5 + knowledge top3, 向量+关键词混合) → 融合客户上下文（画像+最近跟进）
→ strong 模型流式生成 → 附来源引用。

SSE 事件：
- sources：{scripts: [...], knowledge: [...], no_reference: bool} —— 生成前先给出引用（可解释）
- delta：{text}
- done：{llm_call_id}（赞/踩反馈落点）
- error：{message}
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import rag
from app.ai.client import LLMClient, get_llm_client
from app.ai.prompt_loader import render_prompt
from app.core.exceptions import DomainError
from app.models.account import Account
from app.models.activity import Activity
from app.models.enums import ActivityRelatedType, LlmTaskType, ScriptCategory
from app.models.user import User
from app.schemas.script import RecommendRequest
from app.services import script_service
from app.services.account_service import account_service
from app.services.opportunity_service import opportunity_service

logger = logging.getLogger(__name__)

SCENARIO_LABELS = {
    ScriptCategory.OPENING: "开场破冰",
    ScriptCategory.DISCOVERY: "需求挖掘",
    ScriptCategory.OBJECTION: "异议处理",
    ScriptCategory.PRICING: "价格谈判",
    ScriptCategory.CLOSING: "促成交",
    ScriptCategory.RETENTION: "客户维系",
}


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _load_context(
    session: AsyncSession, actor: User, payload: RecommendRequest
) -> tuple[Account | None, list[Activity]]:
    """客户上下文：商机优先（其跟进+所属客户），否则客户直挂跟进。越权由 service 层拦截。"""
    account: Account | None = None
    related: tuple[ActivityRelatedType, uuid.UUID] | None = None
    if payload.opportunity_id:
        opp = await opportunity_service.get(session, actor, payload.opportunity_id)
        account = await session.scalar(select(Account).where(Account.id == opp.account_id))
        related = (ActivityRelatedType.OPPORTUNITY, opp.id)
    elif payload.account_id:
        account = await account_service.get(session, actor, payload.account_id)
        related = (ActivityRelatedType.ACCOUNT, account.id)
    activities: list[Activity] = []
    if related:
        activities = list(
            await session.scalars(
                select(Activity)
                .where(
                    Activity.related_type == related[0],
                    Activity.related_id == related[1],
                    Activity.deleted_at.is_(None),
                )
                .order_by(Activity.created_at.desc())
                .limit(5)
            )
        )
    return account, activities


def _profile_summary(account: Account | None) -> str | None:
    if account is None or not account.ai_profile:
        return None
    parts = []
    if overview := account.ai_profile.get("company_overview"):
        parts.append(str(overview))
    if pain_points := account.ai_profile.get("pain_points"):
        parts.append("痛点：" + "、".join(str(p) for p in pain_points))
    return " ".join(parts)[:300] or None


async def recommend_stream(
    session: AsyncSession,
    actor: User,
    payload: RecommendRequest,
    llm: LLMClient | None = None,
) -> AsyncIterator[str]:
    llm = llm or get_llm_client()
    try:
        account, activities = await _load_context(session, actor, payload)

        query_parts = [SCENARIO_LABELS[payload.scenario]]
        if payload.user_hint:
            query_parts.append(payload.user_hint)
        if account:
            query_parts.append(account.industry or "")
        if activities:
            query_parts.append(activities[0].content[:100])
        query = " ".join(p for p in query_parts if p)

        script_hits = await rag.search_scripts(
            session, query, category=payload.scenario, top_k=5, llm=llm, user_id=actor.id
        )
        knowledge_hits = await rag.search_knowledge(
            session, query, top_k=3, llm=llm, user_id=actor.id
        )

        yield sse_event(
            "sources",
            {
                "no_reference": not script_hits and not knowledge_hits,
                "scripts": [
                    {
                        "id": str(h.script.id),
                        "scenario": h.script.scenario,
                        "preview": h.script.content[:80],
                    }
                    for h in script_hits
                ],
                "knowledge": [
                    {"doc_title": h.doc_title, "preview": h.chunk.content[:80]}
                    for h in knowledge_hits
                ],
            },
        )

        prompt = render_prompt(
            "script_gen.j2",
            channel=payload.channel,
            scenario_label=SCENARIO_LABELS[payload.scenario],
            user_hint=payload.user_hint,
            account_name=account.name if account else None,
            industry=account.industry if account else None,
            profile_summary=_profile_summary(account),
            recent_activities=[
                {"date": a.created_at.strftime("%Y-%m-%d"), "content": a.content}
                for a in activities
            ],
            script_refs=[{"content": h.script.content} for h in script_hits],
            knowledge_refs=[{"content": h.chunk.content} for h in knowledge_hits],
        )

        meta: dict[str, Any] = {}
        async for piece in llm.chat_stream(
            LlmTaskType.SCRIPT_GEN,
            [{"role": "user", "content": prompt}],
            user_id=actor.id,
            meta=meta,
        ):
            yield sse_event("delta", {"text": piece})

        await script_service.bump_usage(session, [h.script.id for h in script_hits])
        yield sse_event("done", {"llm_call_id": meta.get("llm_call_id")})
    except DomainError as exc:
        yield sse_event("error", {"message": exc.message})
    except Exception:
        logger.exception("话术推荐生成失败")
        yield sse_event("error", {"message": "生成失败，请稍后重试"})
