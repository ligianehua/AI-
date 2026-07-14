"""M10 合同 AI 评测（真实调用）：要素抽取 20 条 + 风险审查 8 条。

extract expect：字段值为"应包含的子串"；写 "未提及" 表示该字段必须含「未提及」
（反幻觉：原文没有的信息不许编）。payment_min = payment_terms 最少条数。
review expect：must_flag = risks 全文必须出现的关键词；missing_contains = missing_clauses 必须提到。
"""

import json
from typing import Any

import pytest

from app.ai.client import LLMClient
from app.ai.prompt_loader import render_prompt
from app.ai.schemas import ContractExtractOutput, ContractReviewOutput
from app.models.enums import LlmTaskType
from app.services.contract_service import get_risk_checklist
from evals.conftest import load_golden

EXTRACT_CASES = load_golden("contract_extract")
REVIEW_CASES = load_golden("contract_review")


@pytest.fixture(scope="session")
def eval_llm() -> LLMClient:
    return LLMClient()


@pytest.mark.parametrize("case", EXTRACT_CASES, ids=[c["id"] for c in EXTRACT_CASES])
async def test_contract_extract(
    case: dict[str, Any], require_llm_keys: None, eval_llm: LLMClient
) -> None:
    out = await eval_llm.chat_structured(
        LlmTaskType.CONTRACT_EXTRACT,
        [
            {
                "role": "user",
                "content": render_prompt(
                    "contract_extract.j2", contract_text=case["input"]["text"]
                ),
            }
        ],
        ContractExtractOutput,
    )
    expect = case["expect"]
    field_map = {
        "party_a": out.party_a,
        "party_b": out.party_b,
        "amount": out.amount,
        "sign_date": out.sign_date,
        "period": out.period,
    }
    for key, sub in expect.items():
        if key == "payment_min":
            assert len(out.payment_terms) >= sub, (
                f"{case['id']} 付款条目应 ≥{sub}，实际 {out.payment_terms}"
            )
            continue
        actual = field_map[key]
        assert sub in actual, f"{case['id']} 字段 {key} 应包含「{sub}」，实际「{actual}」"


@pytest.mark.parametrize("case", REVIEW_CASES, ids=[c["id"] for c in REVIEW_CASES])
async def test_contract_review(
    case: dict[str, Any], require_llm_keys: None, eval_llm: LLMClient
) -> None:
    out = await eval_llm.chat_structured(
        LlmTaskType.CONTRACT_REVIEW,
        [
            {
                "role": "user",
                "content": render_prompt(
                    "contract_review.j2",
                    contract_text=case["input"]["text"],
                    checklist=get_risk_checklist(),
                ),
            }
        ],
        ContractReviewOutput,
    )
    expect = case["expect"]
    if flag := expect.get("must_flag"):
        risks_text = json.dumps([r.model_dump() for r in out.risks], ensure_ascii=False)
        assert flag in risks_text, f"{case['id']} risks 应提及「{flag}」，实际：{risks_text[:400]}"
    if missing := expect.get("missing_contains"):
        joined = "、".join(out.missing_clauses)
        assert missing in joined, (
            f"{case['id']} missing_clauses 应提及「{missing}」，实际：{joined}"
        )
    assert "法务" in out.overall_note, (
        f"{case['id']} overall_note 缺法务审核提醒：{out.overall_note}"
    )
