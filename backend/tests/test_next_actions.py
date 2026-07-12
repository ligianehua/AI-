"""AI 下一步建议测试（mock LLM）：三条结构化输出、prompt 事实注入、可见域。"""

import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.client import LLMClient, get_llm_client
from app.main import app
from app.models import Account, Activity, Opportunity, User
from app.models.enums import ActivityRelatedType, ActivityType, OpportunityStage
from tests.conftest import RoleUsers
from tests.fake_llm import FakeOpenAI, completion

LoginFn = Callable[[str], Awaitable[dict[str, str]]]

ACTIONS_JSON = json.dumps(
    {
        "actions": [
            {
                "action": "本周内电话回访王总，确认报价反馈",
                "reason": "跟进记录显示已发送报价单，客户尚未回复",
                "suggested_script_scenario": "pricing",
            },
            {
                "action": "准备竞品对比材料发给客户",
                "reason": "客户提到在对比其他供应商",
                "suggested_script_scenario": "objection",
            },
            {
                "action": "约客户 IT 负责人做技术答疑会议",
                "reason": "跟进记录显示 IT 部门有集成疑问",
                "suggested_script_scenario": None,
            },
        ]
    },
    ensure_ascii=False,
)


async def _seed_opp_with_activities(session: AsyncSession, owner: User) -> Opportunity:
    account = Account(name=f"建议客户-{uuid.uuid4().hex[:6]}", owner_id=owner.id)
    session.add(account)
    await session.flush()
    opp = Opportunity(
        account_id=account.id,
        name="建议测试商机",
        amount=Decimal(200_000),
        stage=OpportunityStage.PROPOSAL,
        probability=50,
        owner_id=owner.id,
        stage_history=[
            {
                "stage": "proposal",
                "entered_at": (datetime.now(UTC) - timedelta(days=5)).isoformat(),
                "by": "test",
            }
        ],
    )
    session.add(opp)
    await session.flush()
    session.add(
        Activity(
            related_type=ActivityRelatedType.OPPORTUNITY,
            related_id=opp.id,
            type=ActivityType.EMAIL,
            content="已发送报价单，等待客户反馈",
            owner_id=owner.id,
        )
    )
    await session.commit()
    return opp


async def test_next_actions_endpoint(
    client: AsyncClient,
    session: AsyncSession,
    roles: RoleUsers,
    login: LoginFn,
    llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
) -> None:
    opp = await _seed_opp_with_activities(session, roles.sales_a)
    fakes["deepseek"].chat.completions.responses = [completion(ACTIONS_JSON)]
    app.dependency_overrides[get_llm_client] = lambda: llm
    try:
        headers = await login("sales_a@test.cn")
        resp = await client.get(f"/api/v1/opportunities/{opp.id}/next-actions", headers=headers)
        assert resp.status_code == 200, resp.text
        actions = resp.json()["actions"]
        assert len(actions) == 3
        assert actions[0]["suggested_script_scenario"] == "pricing"

        # prompt 必须注入真实上下文：阶段/停滞天数/跟进内容
        prompt = fakes["deepseek"].chat.completions.calls[0]["messages"][0]["content"]
        assert "方案报价" in prompt
        assert "已发送报价单" in prompt
        assert "已停留 5 天" in prompt

        # 别人不能看
        resp = await client.get(
            f"/api/v1/opportunities/{opp.id}/next-actions",
            headers=await login("sales_b@test.cn"),
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_llm_client, None)
