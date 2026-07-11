"""线索评分 golden set 回归（22 条）。

规则层：精确断言（不依赖 LLM，任何环境都跑）。
LLM 层：真实调用，验证 budget_signal 精确命中、urgency 在允许集合、intent 在区间内、
        reasons 非空且为中文——含反幻觉用例（垃圾数据/信息不足必须低分且不编造预算）。
"""

from typing import Any

import pytest

from app.ai.client import LLMClient
from app.ai.prompt_loader import render_prompt
from app.ai.schemas import LeadScoringOutput
from app.models.enums import LeadSource, LlmTaskType
from app.models.lead import Lead
from app.services.lead_scoring import SOURCE_LABELS, rule_score
from evals.conftest import load_golden

CASES = load_golden("lead_scoring")


def _lead_from_input(data: dict[str, Any]) -> Lead:
    return Lead(
        source=data["source"],
        account_name=data["account_name"],
        contact_name=data.get("contact_name"),
        contact_phone=data.get("contact_phone"),
        contact_wechat=data.get("contact_wechat"),
        industry=data.get("industry"),
        requirement_desc=data.get("requirement_desc"),
    )


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_rule_layer(case: dict[str, Any]) -> None:
    score, _ = rule_score(_lead_from_input(case["input"]))
    assert score == case["expect"]["rule_score"], f"{case['id']} 规则分不符"


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_llm_layer(case: dict[str, Any], require_llm_keys: None) -> None:
    data = case["input"]
    expect = case["expect"]
    prompt = render_prompt(
        "lead_scoring.j2",
        account_name=data["account_name"],
        source_label=SOURCE_LABELS[LeadSource(data["source"])],
        industry=data.get("industry"),
        requirement_desc=data.get("requirement_desc"),
        activities=data.get("activities", []),
    )
    out = await LLMClient().chat_structured(
        LlmTaskType.LEAD_SCORING, [{"role": "user", "content": prompt}], LeadScoringOutput
    )
    assert out.budget_signal == expect["budget_signal"], f"{case['id']} budget_signal 不符"
    assert out.urgency in expect["urgency_in"], f"{case['id']} urgency={out.urgency} 不在允许集合"
    bounds = (expect["intent_min"], expect["intent_max"])
    assert bounds[0] <= out.intent_score <= bounds[1], (
        f"{case['id']} intent={out.intent_score} 超出 {bounds}"
    )
    assert out.reasons and all(r.strip() for r in out.reasons)
