"""M12 业绩归因 eval（20 条，真实调用）。

断言：输出全文命中 mention_any 其一（归因方向正确）；must_number 出现在输出中
（引用输入真实数字，反幻觉）。
"""

import json
from typing import Any

import pytest

from app.ai.client import LLMClient
from app.ai.prompt_loader import render_prompt
from app.ai.schemas import PerformanceInsightOutput
from app.models.enums import LlmTaskType
from evals.conftest import load_golden

CASES = load_golden("performance_insight")


@pytest.fixture(scope="session")
def eval_llm() -> LLMClient:
    return LLMClient()


def _normalize(text: str) -> str:
    """数字对比容忍格式差异：去掉千分位逗号与空格。"""
    return text.replace(",", "").replace("，", "").replace(" ", "")


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_performance_insight(
    case: dict[str, Any], require_llm_keys: None, eval_llm: LLMClient
) -> None:
    data = case["input"]
    prompt = render_prompt(
        "performance_insight.j2",
        scope_label="个人业绩",
        month=data["current"]["month"],
        prev_month=data["previous"]["month"],
        current=json.dumps(data["current"], ensure_ascii=False),
        previous=json.dumps(data["previous"], ensure_ascii=False),
    )
    out = await eval_llm.chat_structured(
        LlmTaskType.PERFORMANCE_INSIGHT,
        [{"role": "user", "content": prompt}],
        PerformanceInsightOutput,
    )
    full_text = " ".join([out.summary, *out.findings, *out.suggestions])
    expect = case["expect"]

    mentions = expect["mention_any"]
    assert any(m in full_text for m in mentions), (
        f"{case['id']} 输出未命中任一关键词 {mentions}：{full_text[:300]}"
    )
    if number := expect.get("must_number"):
        # 金额可能被改写为「X 万」：50 0000 → 50万 也算引用
        normalized = _normalize(full_text)
        wan = None
        if number.isdigit() and int(number) >= 10000 and int(number) % 1000 == 0:
            value = int(number)
            wan = f"{value / 10000:g}万"
        assert number in normalized or (wan is not None and wan in normalized), (
            f"{case['id']} 输出未引用输入数字 {number}（或 {wan}）：{full_text[:300]}"
        )
