"""下一步建议 golden set 回归（20 条，真实调用 LLM）。

反幻觉断言：
- 正好 3 条建议，action/reason 非空
- 至少一个输入锚点词出现在建议或理由中（证明引用真实跟进内容）
- forbidden 词（输入中不存在的事实）不得出现在理由中
"""

from typing import Any

import pytest

from app.ai.client import LLMClient
from app.ai.prompt_loader import render_prompt
from app.ai.schemas import NextActionOutput
from app.models.enums import LlmTaskType
from evals.conftest import load_golden

CASES = load_golden("next_action")


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_next_actions(case: dict[str, Any], require_llm_keys: None) -> None:
    data = case["input"]
    expect = case["expect"]

    prompt = render_prompt(
        "next_action.j2",
        name=data["name"],
        account_name=data["account_name"],
        stage_label=data["stage_label"],
        stuck_days=data["stuck_days"],
        amount=data["amount"],
        expected_close_date=data.get("expected_close_date"),
        profile_summary=data.get("profile_summary"),
        activities=data.get("activities", []),
    )
    out = await LLMClient().chat_structured(
        LlmTaskType.NEXT_ACTION, [{"role": "user", "content": prompt}], NextActionOutput
    )

    assert len(out.actions) == 3
    combined = " ".join(f"{a.action} {a.reason}" for a in out.actions)
    assert all(a.action.strip() and a.reason.strip() for a in out.actions)

    anchors = expect.get("anchors_any", [])
    if anchors:
        assert any(k in combined for k in anchors), (
            f"{case['id']} 建议未引用任何输入锚点 {anchors}：{combined[:300]}"
        )
    for word in expect.get("forbidden", []):
        assert word not in combined, f"{case['id']} 出现输入中不存在的事实「{word}」（疑似幻觉）"
