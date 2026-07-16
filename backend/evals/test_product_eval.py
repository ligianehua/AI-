"""M13 产品 AI 评测（真实调用）：规格抽取 20 条 + 对比总结 6 条。

extract expect：model_no/brand 为"应包含的子串"（「未提及」为反幻觉断言）；
spec_has=[必须出现的参数名]；spec_absent=[禁止编造出现的参数名]。
compare expect：must_mention=[输出全文须命中的参数值]；must_note_partial=须指出仅部分产品提供。
"""

import json
from typing import Any

import pytest

from app.ai.client import LLMClient
from app.ai.prompt_loader import render_prompt
from app.ai.schemas import ProductCompareOutput, ProductExtractOutput
from app.models.enums import LlmTaskType
from evals.conftest import load_golden

EXTRACT_CASES = load_golden("product_extract")
COMPARE_CASES = load_golden("product_compare")


@pytest.fixture(scope="session")
def eval_llm() -> LLMClient:
    return LLMClient()


@pytest.mark.parametrize("case", EXTRACT_CASES, ids=[c["id"] for c in EXTRACT_CASES])
async def test_product_extract(
    case: dict[str, Any], require_llm_keys: None, eval_llm: LLMClient
) -> None:
    out = await eval_llm.chat_structured(
        LlmTaskType.PRODUCT_EXTRACT,
        [
            {
                "role": "user",
                "content": render_prompt("product_extract.j2", spec_text=case["input"]["text"]),
            }
        ],
        ProductExtractOutput,
    )
    expect = case["expect"]
    if sub := expect.get("model_no"):
        assert sub in out.model_no, f"{case['id']} 型号应含「{sub}」，实际「{out.model_no}」"
    if sub := expect.get("brand"):
        assert sub in out.brand, f"{case['id']} 品牌应含「{sub}」，实际「{out.brand}」"
    spec_keys = "｜".join(out.specs.keys())
    for key in expect.get("spec_has", []):
        assert any(key in k for k in out.specs), (
            f"{case['id']} specs 应含参数「{key}」，实际键：{spec_keys}"
        )
    for key in expect.get("spec_absent", []):
        assert not any(key in k for k in out.specs), (
            f"{case['id']} specs 不应编造参数「{key}」：{spec_keys}"
        )


@pytest.mark.parametrize("case", COMPARE_CASES, ids=[c["id"] for c in COMPARE_CASES])
async def test_product_compare(
    case: dict[str, Any], require_llm_keys: None, eval_llm: LLMClient
) -> None:
    out = await eval_llm.chat_structured(
        LlmTaskType.PRODUCT_COMPARE,
        [
            {
                "role": "user",
                "content": render_prompt(
                    "product_compare.j2",
                    matrix=json.dumps(case["input"]["matrix"], ensure_ascii=False, indent=1),
                ),
            }
        ],
        ProductCompareOutput,
    )
    full_text = " ".join([out.summary, *out.key_differences, out.recommendation])
    expect = case["expect"]
    for value in expect.get("must_mention", []):
        assert value in full_text, f"{case['id']} 输出应引用参数值「{value}」：{full_text[:300]}"
    if partial := expect.get("must_note_partial"):
        assert partial in full_text, (
            f"{case['id']} 应指出「{partial}」仅部分产品提供：{full_text[:300]}"
        )
