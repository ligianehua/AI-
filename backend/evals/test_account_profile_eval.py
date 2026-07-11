"""客户画像 golden set 回归（20 条，真实调用 LLM）。

反幻觉断言：
- decision_chain 联系人必须 ⊆ 输入联系人（禁止编造人名）
- 无联系人时决策链必须为空
- confidence_note 必须注明实际跟进记录条数
- 稀疏数据（<3 条跟进）必须明确提示信息不足/可靠性有限，而非硬编
"""

from typing import Any

import pytest

from app.ai.client import LLMClient
from app.ai.prompt_loader import render_prompt
from app.ai.schemas import AccountProfileOutput
from app.models.enums import LlmTaskType
from evals.conftest import load_golden

CASES = load_golden("account_profile")

INSUFFICIENT_MARKERS = [
    "信息不足",
    "可靠性有限",
    "记录过少",
    "记录较少",
    "无法判断",
    "暂无",
    "缺乏",
]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_profile_generation(case: dict[str, Any], require_llm_keys: None) -> None:
    data = case["input"]
    expect = case["expect"]

    prompt = render_prompt(
        "account_profile.j2",
        name=data["name"],
        industry=data.get("industry"),
        size=data.get("size"),
        region=data.get("region"),
        remark=data.get("remark"),
        activity_count=expect["activity_count"],
        contacts=data.get("contacts", []),
        activities=data.get("activities", []),
    )
    out = await LLMClient().chat_structured(
        LlmTaskType.ACCOUNT_PROFILE, [{"role": "user", "content": prompt}], AccountProfileOutput
    )

    # 1) 决策链不得编造人名
    known = set(expect["known_contacts"])
    chain_names = {item.contact for item in out.decision_chain}
    assert chain_names <= known, f"{case['id']} 决策链编造了联系人：{chain_names - known}"
    if not known:
        assert out.decision_chain == [], f"{case['id']} 无联系人却生成了决策链"

    # 2) 置信说明必须注明条数
    assert str(expect["activity_count"]) in out.confidence_note, (
        f"{case['id']} confidence_note 未注明 {expect['activity_count']} 条：{out.confidence_note}"
    )

    # 3) 稀疏数据必须承认信息不足
    if expect["sparse"]:
        combined = " ".join(
            [out.company_overview, out.cooperation_stage_analysis, out.confidence_note]
        )
        assert any(marker in combined for marker in INSUFFICIENT_MARKERS), (
            f"{case['id']} 跟进仅 {expect['activity_count']} 条却未提示信息不足：{combined[:200]}"
        )
