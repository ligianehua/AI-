"""AI 画像生成测试（mock LLM）：落库、prompt 事实注入、稀疏数据铁律、失败保留旧画像。"""

import json
import uuid

import httpx
import openai
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.ai.client import LLMClient
from app.core.exceptions import LLMUnavailableError
from app.models import Account, Activity, Contact, User
from app.models.enums import ActivityRelatedType, ActivityType
from app.services.account_profile import generate_profile
from app.tasks.profile import account_profile_task
from tests.conftest import RoleUsers
from tests.fake_llm import FakeOpenAI, completion

REQ = httpx.Request("POST", "https://fake.test/v1/chat/completions")

PROFILE_JSON = json.dumps(
    {
        "company_overview": "华东制造企业，正在做销售数字化",
        "pain_points": ["销售过程不透明"],
        "decision_chain": [{"contact": "王决策", "role": "决策人", "attitude": "积极"}],
        "cooperation_stage_analysis": "处于方案沟通阶段",
        "risks": ["竞品在接触"],
        "suggestions": ["尽快安排产品演示"],
        "confidence_note": "基于 3 条跟进记录，预算信息不足",
    },
    ensure_ascii=False,
)


async def _seed_account_with_data(
    session: AsyncSession, owner: User, activity_count: int = 3
) -> Account:
    account = Account(name=f"画像客户-{uuid.uuid4().hex[:6]}", industry="制造业", owner_id=owner.id)
    session.add(account)
    await session.flush()
    session.add(
        Contact(account_id=account.id, name="王决策", title="总经理", role_in_deal="decision_maker")
    )
    for i in range(activity_count):
        session.add(
            Activity(
                related_type=ActivityRelatedType.ACCOUNT,
                related_id=account.id,
                type=ActivityType.VISIT,
                content=f"第 {i + 1} 次拜访，聊了数字化需求",
                owner_id=owner.id,
            )
        )
    await session.commit()
    return account


async def test_generate_profile_saves_validated_output(
    session: AsyncSession, roles: RoleUsers, llm: LLMClient, fakes: dict[str, FakeOpenAI]
) -> None:
    account = await _seed_account_with_data(session, roles.sales_a, activity_count=3)
    fakes["qwen"].chat.completions.responses = [completion(PROFILE_JSON)]
    fakes["deepseek"].chat.completions.responses = [completion(PROFILE_JSON)]

    profile = await generate_profile(session, roles.sales_a, account.id, llm=llm)
    assert profile.decision_chain[0].contact == "王决策"

    await session.refresh(account)
    assert account.ai_profile is not None
    assert account.ai_profile["company_overview"].startswith("华东制造")
    assert account.ai_profile_updated_at is not None

    # prompt 必须带入客户事实与联系人（strong 档路由到 deepseek 默认供应商）
    sent_calls = fakes["deepseek"].chat.completions.calls or fakes["qwen"].chat.completions.calls
    prompt = sent_calls[0]["messages"][0]["content"]
    assert account.name in prompt
    assert "王决策" in prompt
    assert "共 3 条" in prompt


async def test_generate_profile_sparse_data_rules_in_prompt(
    session: AsyncSession, roles: RoleUsers, llm: LLMClient, fakes: dict[str, FakeOpenAI]
) -> None:
    """跟进 < 3 条时，prompt 必须注入"可靠性有限"铁律（模型端行为由 eval 验证）。"""
    account = await _seed_account_with_data(session, roles.sales_a, activity_count=1)
    fakes["deepseek"].chat.completions.responses = [completion(PROFILE_JSON)]

    await generate_profile(session, roles.sales_a, account.id, llm=llm)
    prompt = fakes["deepseek"].chat.completions.calls[0]["messages"][0]["content"]
    assert "跟进记录不足 3 条" in prompt
    assert "可靠性有限" in prompt


async def test_generate_profile_failure_keeps_old_profile(
    session: AsyncSession, roles: RoleUsers, llm: LLMClient, fakes: dict[str, FakeOpenAI]
) -> None:
    account = await _seed_account_with_data(session, roles.sales_a)
    old_profile = {"company_overview": "旧画像"}
    account.ai_profile = old_profile
    await session.commit()

    err = openai.InternalServerError("down", response=httpx.Response(500, request=REQ), body=None)
    fakes["deepseek"].chat.completions.responses = [err]
    fakes["qwen"].chat.completions.responses = [
        openai.APIConnectionError(message="down", request=REQ)
    ]
    with pytest.raises(LLMUnavailableError):
        await generate_profile(session, roles.sales_a, account.id, llm=llm)

    await session.refresh(account)
    assert account.ai_profile == old_profile  # 失败不覆盖旧画像


async def test_account_profile_task_entrypoint(
    engine: AsyncEngine,
    session: AsyncSession,
    roles: RoleUsers,
    llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
) -> None:
    account = await _seed_account_with_data(session, roles.sales_a)
    fakes["deepseek"].chat.completions.responses = [completion(PROFILE_JSON)]

    maker = async_sessionmaker(engine, expire_on_commit=False)
    await account_profile_task({"sessionmaker": maker, "llm": llm}, str(account.id))

    await session.refresh(account)
    assert account.ai_profile is not None
    assert account.ai_profile["confidence_note"].startswith("基于")
