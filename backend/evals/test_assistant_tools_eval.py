"""M9 助手工具选择 eval（22 条，真实调用）：断言首个工具调用的名称与关键参数。

expect 字段：
- tool：必须命中的工具名
- args_eq：参数精确相等（如 stage=lost）
- args_has：参数必须出现的键（值不校验，如 min_score）
- args_contains：参数值必须包含的子串（如客户名关键词）
"""

import json
from typing import Any

import pytest

from app.ai.client import LLMClient
from app.ai.prompt_loader import render_prompt
from app.models.enums import LlmTaskType
from app.services.assistant_service import TOOLS
from evals.conftest import load_golden

CASES = load_golden("assistant_tools")


@pytest.fixture(scope="session")
def eval_llm() -> LLMClient:
    return LLMClient()


def _system_prompt() -> str:
    return render_prompt(
        "assistant_chat.j2", user_name="李小销", role_label="销售", today="2026-07-14"
    )


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_first_tool_selection(
    case: dict[str, Any], require_llm_keys: None, eval_llm: LLMClient
) -> None:
    result = await eval_llm.chat_tools(
        LlmTaskType.CHAT,
        [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": case["input"]["question"]},
        ],
        TOOLS,
    )
    expect = case["expect"]
    assert result.tool_calls, (
        f"{case['id']} 未调用任何工具，直接回复了：{result.content[:200]}"
    )
    first = result.tool_calls[0]
    assert first.name == expect["tool"], (
        f"{case['id']} 期望工具 {expect['tool']}，实际 {first.name}({first.arguments})"
    )
    args = json.loads(first.arguments or "{}")
    for key, value in expect.get("args_eq", {}).items():
        assert args.get(key) == value, f"{case['id']} 参数 {key} 期望 {value}，实际 {args}"
    for key in expect.get("args_has", []):
        assert args.get(key) is not None, f"{case['id']} 参数缺少 {key}：{args}"
    for key, sub in expect.get("args_contains", {}).items():
        assert sub in str(args.get(key, "")), (
            f"{case['id']} 参数 {key} 应包含「{sub}」，实际 {args}"
        )
