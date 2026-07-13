"""检索质量抽查（20 条，真实嵌入 + 真 PG）：期望话术必须出现在 top-5。

对应 PLAN M6 DoD「top-5 命中人工评 ≥80%」的自动化部分；人工抽查在真实话术库
灌入后由业务方执行。
"""

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import rag
from app.ai.client import LLMClient
from app.core.security import hash_password
from app.models.script import Script
from app.models.user import User
from evals.conftest import load_golden
from scripts.seed_scripts import SAMPLES

CASES = load_golden("script_search")


@pytest.fixture(scope="session")
def eval_llm() -> LLMClient:
    return LLMClient()


@pytest.fixture(scope="session")
async def seeded_scripts(
    engine: Any, require_llm_keys: None, eval_llm: LLMClient
) -> dict[str, str]:
    """12 条示例话术 + 真实嵌入，整个评测会话只播种一次（幂等：重复运行先清旧数据）。

    返回 scenario -> content 映射。
    """
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    # 与生产索引文本一致（embed_script_task）：标题+正文
    contents = [f"{scenario}\n{content}" for _, scenario, content, _ in SAMPLES]
    try:
        vectors = await eval_llm.embed(contents)
    except Exception as exc:  # 嵌入档位不可用 → 整组跳过
        pytest.skip(f"嵌入不可用，检索质量 eval 跳过：{exc}")

    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        await session.execute(delete(Script))
        admin = await session.scalar(select(User).where(User.email == "eval_admin@test.cn"))
        if admin is None:
            admin = User(
                name="评测管理员",
                email="eval_admin@test.cn",
                hashed_password=hash_password("password123"),
                role="admin",
            )
            session.add(admin)
            await session.flush()
        for (category, scenario, content, tags), vector in zip(SAMPLES, vectors, strict=True):
            session.add(
                Script(
                    category=category,
                    scenario=scenario,
                    content=content,
                    tags=tags,
                    created_by=admin.id,
                    embedding=vector,
                )
            )
        await session.commit()
    return {scenario: content for _, scenario, content, _ in SAMPLES}


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_search_top5_hit(
    case: dict[str, Any],
    session: AsyncSession,
    seeded_scripts: dict[str, str],
    eval_llm: LLMClient,
) -> None:
    hits = await rag.search_scripts(
        session,
        case["input"]["query"],
        category=case["input"].get("category"),
        top_k=5,
        llm=eval_llm,
    )
    scenarios = [h.script.scenario for h in hits]
    assert case["expect"]["scenario"] in scenarios, (
        f"{case['id']} 查询「{case['input']['query']}」top-5 未命中"
        f"期望「{case['expect']['scenario']}」，实际：{scenarios}"
    )
