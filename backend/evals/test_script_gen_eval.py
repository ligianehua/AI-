"""话术生成质量 eval（真实调用）：格式、渠道文风规则断言 + LLM-as-judge 评分。"""

from typing import Any

import pytest
from pydantic import BaseModel, Field

from app.ai.client import LLMClient
from app.ai.prompt_loader import render_prompt
from app.models.enums import LlmTaskType

CASES: list[dict[str, Any]] = [
    {
        "id": "sg-wechat-1",
        "channel": "wechat",
        "scenario_label": "价格谈判",
        "user_hint": "客户嫌贵，预算 10 万，我们报价 15 万",
        "refs": ["理解您的顾虑。咱们换个算法：按人效提升算，一年省的时间成本远超系统费用。"],
    },
    {
        "id": "sg-wechat-2",
        "channel": "wechat",
        "scenario_label": "客户维系",
        "user_hint": "客户三个月没登录系统了",
        "refs": [],
    },
    {
        "id": "sg-email-1",
        "channel": "email",
        "scenario_label": "促成交",
        "user_hint": "方案已确认，推动本月签约",
        "refs": ["月底前签约可赶上本期实施排期，晚了要等下个月。"],
    },
    {
        "id": "sg-email-2",
        "channel": "email",
        "scenario_label": "需求挖掘",
        "user_hint": "初次沟通后发邮件约调研会",
        "refs": [],
    },
    {
        "id": "sg-phone-1",
        "channel": "phone",
        "scenario_label": "开场破冰",
        "user_hint": "陌生拜访制造业客户",
        "refs": ["占用您一分钟——我们帮同行业企业把跟单效率提升了 30%。"],
    },
    {
        "id": "sg-phone-2",
        "channel": "phone",
        "scenario_label": "异议处理",
        "user_hint": "客户说已经在用竞品",
        "refs": [],
    },
]


class JudgeOutput(BaseModel):
    score: int = Field(ge=1, le=5, description="综合质量 1-5 分")
    reason: str


JUDGE_PROMPT = """你是销售话术质量评审。给下面的话术候选打 1-5 分（5 最好）。
评分维度：是否贴合场景、是否具体可用、渠道文风是否正确（{channel_rule}）、是否有编造事实。
3 分及以上表示可用。只输出 JSON：{{"score": 1-5, "reason": "……"}}

场景：{scenario}
渠道：{channel}
候选话术：
{content}
"""

CHANNEL_RULES = {
    "wechat": "微信应口语化短句，无书面敬语与 markdown",
    "email": "邮件应正式结构化，含称呼与落款",
    "phone": "电话应为自然口语稿",
}


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_script_generation_quality(case: dict[str, Any], require_llm_keys: None) -> None:
    llm = LLMClient()
    prompt = render_prompt(
        "script_gen.j2",
        channel=case["channel"],
        scenario_label=case["scenario_label"],
        user_hint=case["user_hint"],
        account_name=None,
        industry=None,
        profile_summary=None,
        recent_activities=[],
        script_refs=[{"content": r} for r in case["refs"]],
        knowledge_refs=[],
    )
    result = await llm.chat(LlmTaskType.SCRIPT_GEN, [{"role": "user", "content": prompt}])
    text = result.content

    # 结构断言：三条候选
    for marker in ("【候选1】", "【候选2】", "【候选3】"):
        assert marker in text, f"{case['id']} 缺少 {marker}：{text[:200]}"

    # 渠道文风规则断言
    if case["channel"] == "wechat":
        assert "尊敬的" not in text, f"{case['id']} 微信话术出现书面敬语"
        assert "##" not in text, f"{case['id']} 微信话术不应有 markdown 标题"
    if case["channel"] == "email":
        assert any(k in text for k in ("您好", "尊敬的")), f"{case['id']} 邮件缺少称呼"

    # LLM-as-judge：逐条 ≥3 分
    candidates = [c.strip() for c in text.split("【候选")[1:]]
    for i, candidate in enumerate(candidates[:3], start=1):
        judge = await llm.chat_structured(
            LlmTaskType.SCRIPT_GEN,
            [
                {
                    "role": "user",
                    "content": JUDGE_PROMPT.format(
                        channel_rule=CHANNEL_RULES[case["channel"]],
                        scenario=case["scenario_label"],
                        channel=case["channel"],
                        content=candidate[:800],
                    ),
                }
            ],
            JudgeOutput,
        )
        assert judge.score >= 3, f"{case['id']} 候选{i} 评分 {judge.score}：{judge.reason}"
