"""线索评分：规则层（0-40，权重配置化）+ LLM 语义层（0-60）。

冷启动诚实原则（PLAN.md §6.1 / §10）：无成交数据校准前这是"专家规则 + 语义判断"，
UI 标注"参考分"；LLM 不可用时降级为纯规则分并在 score_detail.note 里说明。
"""

import logging
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, get_llm_client
from app.ai.prompt_loader import render_prompt
from app.ai.schemas import LeadScoringOutput
from app.core.exceptions import DomainError, NotFoundError
from app.models.activity import Activity
from app.models.enums import ActivityRelatedType, ActivityType, LeadSource, LlmTaskType
from app.models.lead import Lead

logger = logging.getLogger(__name__)

_RULES_FILE = Path(__file__).parent / "scoring_rules.yaml"

SOURCE_LABELS = {
    LeadSource.WEBSITE: "官网咨询",
    LeadSource.EXHIBITION: "展会",
    LeadSource.REFERRAL: "转介绍",
    LeadSource.ADS: "广告",
    LeadSource.COLD_CALL: "陌拜",
    LeadSource.OTHER: "其他",
}
ACTIVITY_TYPE_LABELS = {
    ActivityType.CALL: "电话",
    ActivityType.VISIT: "拜访",
    ActivityType.WECHAT: "微信",
    ActivityType.EMAIL: "邮件",
    ActivityType.MEETING: "会议",
    ActivityType.OTHER: "其他",
}

URGENCY_SCORE = {"high": 10, "medium": 5, "low": 0}
BUDGET_SCORE = 10


class ScoringRules(BaseModel):
    completeness: dict[str, int]
    requirement_min_length: int
    source_weights: dict[str, int]
    industry_match: dict[str, Any]
    max_rule_score: int


@lru_cache
def get_scoring_rules() -> ScoringRules:
    data = yaml.safe_load(_RULES_FILE.read_text(encoding="utf-8"))
    return ScoringRules.model_validate(data)


def rule_score(lead: Lead) -> tuple[int, dict[str, int]]:
    """规则层（纯函数，可独立测试）。返回 (得分, 明细)。"""
    rules = get_scoring_rules()
    breakdown: dict[str, int] = {}

    comp = rules.completeness
    if lead.contact_phone:
        breakdown["有手机号"] = comp.get("contact_phone", 0)
    if lead.contact_wechat:
        breakdown["有微信"] = comp.get("contact_wechat", 0)
    if lead.contact_name:
        breakdown["有联系人"] = comp.get("contact_name", 0)
    if lead.requirement_desc and len(lead.requirement_desc) >= rules.requirement_min_length:
        breakdown["需求描述完整"] = comp.get("requirement_desc", 0)

    source_weight = rules.source_weights.get(lead.source, 0)
    if source_weight:
        breakdown[f"来源：{SOURCE_LABELS.get(LeadSource(lead.source), lead.source)}"] = (
            source_weight
        )

    industries: list[str] = rules.industry_match.get("industries", [])
    if lead.industry and lead.industry in industries:
        breakdown["目标行业"] = int(rules.industry_match.get("weight", 0))

    total = min(sum(breakdown.values()), rules.max_rule_score)
    return total, breakdown


def llm_score_value(out: LeadScoringOutput) -> int:
    """LLM 语义层映射为 0-60 分。"""
    return (
        out.intent_score + (BUDGET_SCORE if out.budget_signal else 0) + URGENCY_SCORE[out.urgency]
    )


async def _recent_activities(session: AsyncSession, lead_id: uuid.UUID) -> list[dict[str, str]]:
    rows = await session.scalars(
        select(Activity)
        .where(
            Activity.related_type == ActivityRelatedType.LEAD,
            Activity.related_id == lead_id,
            Activity.deleted_at.is_(None),
        )
        .order_by(Activity.created_at.desc())
        .limit(10)
    )
    return [
        {
            "date": a.created_at.strftime("%Y-%m-%d"),
            "type_label": ACTIVITY_TYPE_LABELS.get(ActivityType(a.type), a.type),
            "content": a.content,
        }
        for a in rows
    ]


async def score_lead(
    session: AsyncSession, lead_id: uuid.UUID, llm: LLMClient | None = None
) -> None:
    """计算并落库线索评分。LLM 层失败时降级为纯规则分（note 说明）。"""
    lead = await session.scalar(select(Lead).where(Lead.id == lead_id, Lead.deleted_at.is_(None)))
    if lead is None:
        raise NotFoundError("线索不存在")

    rule_total, breakdown = rule_score(lead)

    llm = llm or get_llm_client()
    llm_detail: dict[str, Any] | None = None
    llm_total = 0
    note: str | None = None
    try:
        activities = await _recent_activities(session, lead.id)
        prompt = render_prompt(
            "lead_scoring.j2",
            account_name=lead.account_name,
            source_label=SOURCE_LABELS.get(LeadSource(lead.source), lead.source),
            industry=lead.industry,
            requirement_desc=lead.requirement_desc,
            activities=activities,
        )
        out = await llm.chat_structured(
            LlmTaskType.LEAD_SCORING,
            [{"role": "user", "content": prompt}],
            LeadScoringOutput,
            user_id=lead.owner_id,
        )
        llm_total = llm_score_value(out)
        llm_detail = out.model_dump()
    except DomainError as exc:
        note = f"LLM 暂不可用（{exc.message}），当前为纯规则参考分"
        logger.warning("线索 %s LLM 评分失败：%s", lead_id, exc.message)

    lead.score = rule_total + llm_total
    lead.score_detail = {
        "version": 1,
        "rule_score": rule_total,
        "rule_breakdown": breakdown,
        "llm_score": llm_total if llm_detail else None,
        "llm": llm_detail,
        "note": note,
        "scored_at": datetime.now(UTC).isoformat(),
    }
    await session.commit()
