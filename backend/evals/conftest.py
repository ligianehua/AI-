"""evals：golden set 回归评测（真实调用 LLM，不 mock）。

运行方式：make eval（等价 `uv run pytest evals -m eval`）
纪律（PLAN.md §3）：
- 每个 AI 场景一个 golden set（≥20 条），存 evals/golden/<task>.jsonl
- 改 backend/app/ai/prompts/ 下任何文件必须重跑，通过率下降就回滚或修
- 结构化字段用断言判分；生成质量用 LLM-as-judge
- 未配置 API key 时整组 skip（不算通过，CI 里注意）
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from app.ai.config import get_ai_config

GOLDEN_DIR = Path(__file__).parent / "golden"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(pytest.mark.eval)


def load_golden(name: str) -> list[dict[str, Any]]:
    """读取 golden set（jsonl，一行一用例：{"id", "input", "expect"}）。"""
    path = GOLDEN_DIR / f"{name}.jsonl"
    cases = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                cases.append(json.loads(line))
    return cases


@pytest.fixture(scope="session")
def require_llm_keys() -> None:
    cfg = get_ai_config()
    if not any(os.environ.get(p.api_key_env) for p in cfg.providers.values()):
        pytest.skip("未配置任何 LLM API key（.env），跳过 evals")
