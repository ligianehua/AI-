"""评分逻辑测试：规则层纯函数 + 全流程（mock LLM）+ LLM 不可用降级。"""

import json

import httpx
import openai
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.ai.client import LLMClient
from app.ai.schemas import LeadScoringOutput
from app.models.enums import LeadSource, LeadStatus
from app.models.lead import Lead
from app.services.lead_scoring import llm_score_value, rule_score, score_lead
from app.tasks.scoring import score_lead_task
from tests.conftest import RoleUsers
from tests.fake_llm import FakeOpenAI, completion

REQ = httpx.Request("POST", "https://fake.test/v1/chat/completions")


def _lead(**kwargs: object) -> Lead:
    defaults: dict[str, object] = {
        "source": LeadSource.OTHER,
        "account_name": "测试公司",
        "contact_name": None,
        "contact_phone": None,
        "contact_wechat": None,
        "industry": None,
        "requirement_desc": None,
    }
    defaults.update(kwargs)
    return Lead(**defaults)


def test_rule_score_full_lead_caps_at_40() -> None:
    lead = _lead(
        source=LeadSource.REFERRAL,
        contact_name="王总",
        contact_phone="13800000001",
        contact_wechat="wx_1",
        industry="制造业",
        requirement_desc="需要一套 CRM 系统，管理销售流程，预算充足",
    )
    score, breakdown = rule_score(lead)
    assert score == 40  # 8+4+4+12+12+4=44 → 封顶 40
    assert "来源：转介绍" in breakdown


def test_rule_score_minimal_lead() -> None:
    score, breakdown = rule_score(_lead(source=LeadSource.ADS))
    assert score == 4
    assert breakdown == {"来源：广告": 4}


def test_rule_score_short_requirement_not_counted() -> None:
    lead = _lead(source=LeadSource.WEBSITE, contact_phone="13800000002", requirement_desc="要CRM")
    score, _ = rule_score(lead)
    assert score == 8 + 5  # 短描述（<10 字）不计分


def test_llm_score_value_mapping() -> None:
    out = LeadScoringOutput(
        intent_score=30, budget_signal=True, urgency="high", reasons=["预算明确"]
    )
    assert llm_score_value(out) == 30 + 10 + 10
    out2 = LeadScoringOutput(
        intent_score=5, budget_signal=False, urgency="low", reasons=["信息不足"]
    )
    assert llm_score_value(out2) == 5


async def test_score_lead_full_flow(
    session: AsyncSession, roles: RoleUsers, llm: LLMClient, fakes: dict[str, FakeOpenAI]
) -> None:
    lead = _lead(
        source=LeadSource.REFERRAL,
        contact_phone="13800000003",
        requirement_desc="需要 CRM 系统管理 200 人团队，预算 30 万，下月上线",
        owner_id=roles.sales_a.id,
        status=LeadStatus.NEW,
    )
    session.add(lead)
    await session.commit()

    fakes["deepseek"].chat.completions.responses = [
        completion(
            json.dumps(
                {
                    "intent_score": 35,
                    "budget_signal": True,
                    "urgency": "high",
                    "reasons": ["预算 30 万明确", "下月上线，时间紧迫"],
                },
                ensure_ascii=False,
            )
        )
    ]
    await score_lead(session, lead.id, llm=llm)
    await session.refresh(lead)

    rule_total, _ = rule_score(lead)
    assert lead.score == rule_total + 35 + 10 + 10
    assert lead.score_detail is not None
    assert lead.score_detail["rule_score"] == rule_total
    assert lead.score_detail["llm"]["budget_signal"] is True
    assert lead.score_detail["note"] is None
    # prompt 里带上了线索事实
    sent = fakes["deepseek"].chat.completions.calls[0]["messages"][0]["content"]
    assert "预算 30 万" in sent


async def test_score_lead_degrades_to_rule_only_when_llm_down(
    session: AsyncSession, roles: RoleUsers, llm: LLMClient, fakes: dict[str, FakeOpenAI]
) -> None:
    lead = _lead(
        source=LeadSource.EXHIBITION,
        contact_phone="13800000004",
        owner_id=roles.sales_a.id,
        status=LeadStatus.NEW,
    )
    session.add(lead)
    await session.commit()

    err = openai.InternalServerError("down", response=httpx.Response(500, request=REQ), body=None)
    fakes["deepseek"].chat.completions.responses = [err]
    fakes["qwen"].chat.completions.responses = [
        openai.APIConnectionError(message="down", request=REQ)
    ]
    await score_lead(session, lead.id, llm=llm)
    await session.refresh(lead)

    assert lead.score == 8 + 8  # 纯规则分
    assert lead.score_detail is not None
    assert lead.score_detail["llm"] is None
    assert "LLM 暂不可用" in lead.score_detail["note"]


async def test_score_lead_task_entrypoint(
    engine: AsyncEngine,
    session: AsyncSession,
    roles: RoleUsers,
    llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
) -> None:
    lead = _lead(source=LeadSource.WEBSITE, owner_id=roles.sales_a.id, status=LeadStatus.NEW)
    session.add(lead)
    await session.commit()

    fakes["deepseek"].chat.completions.responses = [
        completion(
            '{"intent_score": 3, "budget_signal": false, "urgency": "low", "reasons": ["信息不足"]}'
        )
    ]
    maker = async_sessionmaker(engine, expire_on_commit=False)
    await score_lead_task({"sessionmaker": maker, "llm": llm}, str(lead.id))

    refreshed = await session.scalar(select(Lead).where(Lead.id == lead.id))
    assert refreshed is not None and refreshed.score == 5 + 3
