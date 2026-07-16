"""M14 咨询助手工具选择 eval（20 条，真实调用）：售前→产品工具，售后→知识库。"""

import json
from typing import Any

import pytest

from app.ai.client import LLMClient
from app.ai.prompt_loader import render_prompt
from app.models.enums import LlmTaskType
from app.services.product_advisor_service import TOOLS
from evals.conftest import load_golden

CASES = load_golden("advisor_tools")


@pytest.fixture(scope="session")
def eval_llm() -> LLMClient:
    return LLMClient()


def _system_prompt() -> str:
    return render_prompt("product_advisor.j2", user_name="李小销", today="2026-07-16")


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_first_tool_selection(
    case: dict[str, Any], require_llm_keys: None, eval_llm: LLMClient
) -> None:
    result = await eval_llm.chat_tools(
        LlmTaskType.PRODUCT_ADVISOR,
        [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": case["input"]["question"]},
        ],
        TOOLS,
    )
    expect = case["expect"]
    assert result.tool_calls, f"{case['id']} 未调用任何工具：{result.content[:200]}"
    first = result.tool_calls[0]
    # tool_in：多步规划下多个首选工具皆合理的用例（如「对比」可先查单品详情）
    acceptable = expect.get("tool_in") or [expect["tool"]]
    assert first.name in acceptable, (
        f"{case['id']} 期望工具 {acceptable}，实际 {first.name}({first.arguments})"
    )
    args = json.loads(first.arguments or "{}")
    for key, sub in expect.get("args_contains", {}).items():
        assert sub in str(args.get(key, "")), (
            f"{case['id']} 参数 {key} 应包含「{sub}」，实际 {args}"
        )
