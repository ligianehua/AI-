"""M10 合同处理：上传→抽取→审查全流程、RBAC、失败重试、草稿生成。"""

import io
import json
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.ai.client import LLMClient
from app.models import Account, Contract, Opportunity
from app.models.enums import ContractStatus, OpportunityStage
from app.services.contract_service import CONTRACT_UPLOAD_DIR
from app.tasks import dispatcher
from app.tasks.contract import process_contract_task
from tests.conftest import RoleUsers
from tests.fake_llm import FakeOpenAI, completion

LoginFn = Callable[[str], Awaitable[dict[str, str]]]

EXTRACT_JSON = json.dumps(
    {
        "party_a": "杭州云帆科技有限公司",
        "party_b": "XX 软件服务有限公司",
        "amount": "人民币壹拾伍万元整（¥150,000.00）",
        "period": "自签署之日起 12 个月",
        "sign_date": "未提及",
        "payment_terms": ["签署后 7 日内支付 50%", "验收后支付 50%"],
        "other_key_terms": ["保密期 2 年"],
        "confidence_note": "签署日期原文未提及",
    },
    ensure_ascii=False,
)

REVIEW_JSON = json.dumps(
    {
        "risks": [
            {
                "clause_quote": "甲方有权单方解除本合同且无需承担任何责任",
                "level": "high",
                "issue": "单方解除权失衡，乙方无补偿",
                "suggestion": "增加解除补偿条款或双向解除权",
            }
        ],
        "missing_clauses": ["未约定违约责任"],
        "overall_note": "存在高风险条款，正式签署前须经法务审核。",
    },
    ensure_ascii=False,
)

CONTRACT_TEXT = "甲方：杭州云帆科技有限公司…甲方有权单方解除本合同且无需承担任何责任…"


@pytest.fixture(autouse=True)
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[Any, ...]]]:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_enqueue(task_name: str, *args: Any) -> bool:
        calls.append((task_name, args))
        return True

    monkeypatch.setattr(dispatcher, "enqueue", fake_enqueue)
    return calls


async def test_upload_process_and_rbac(
    client: AsyncClient,
    session: AsyncSession,
    engine: AsyncEngine,
    roles: RoleUsers,
    login: LoginFn,
    llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
    enqueued: list[tuple[str, tuple[Any, ...]]],
) -> None:
    headers_a = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/contracts/upload",
        files={"file": ("采购合同.txt", io.BytesIO(CONTRACT_TEXT.encode("utf-8")), "text/plain")},
        headers=headers_a,
    )
    assert resp.status_code == 201, resp.text
    contract_id = resp.json()["id"]
    assert resp.json()["status"] == "processing"
    assert enqueued == [("process_contract_task", (contract_id,))]

    # 跑处理任务（extract fast + review strong，fake 队列按序吐出）
    fakes["deepseek"].chat.completions.responses = [
        completion(EXTRACT_JSON),
        completion(REVIEW_JSON),
    ]
    maker = async_sessionmaker(engine, expire_on_commit=False)
    await process_contract_task({"sessionmaker": maker, "llm": llm}, contract_id)

    resp = await client.get(f"/api/v1/contracts/{contract_id}", headers=headers_a)
    body = resp.json()
    assert body["status"] == "ready"
    assert body["extracted"]["party_a"] == "杭州云帆科技有限公司"
    assert body["extracted"]["sign_date"] == "未提及"
    assert body["review"]["risks"][0]["level"] == "high"
    assert "未约定违约责任" in body["review"]["missing_clauses"]

    # RBAC：跨团队销售看不到；同团队主管与 admin 可见
    headers_b = await login("sales_b@test.cn")
    resp = await client.get("/api/v1/contracts", headers=headers_b)
    assert resp.json()["total"] == 0
    resp = await client.get(f"/api/v1/contracts/{contract_id}", headers=headers_b)
    assert resp.status_code == 404
    for email in ("manager_a@test.cn", "admin@test.cn"):
        resp = await client.get("/api/v1/contracts", headers=await login(email))
        assert resp.json()["total"] == 1, email


async def test_upload_rejects_bad_type(
    client: AsyncClient, roles: RoleUsers, login: LoginFn
) -> None:
    headers = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/contracts/upload",
        files={"file": ("photo.png", io.BytesIO(b"xx"), "image/png")},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "不支持的文件类型" in resp.json()["message"]


async def test_task_failure_marks_failed_and_reprocess(
    client: AsyncClient,
    session: AsyncSession,
    engine: AsyncEngine,
    roles: RoleUsers,
    login: LoginFn,
    llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
    enqueued: list[tuple[str, tuple[Any, ...]]],
) -> None:
    contract = Contract(name="坏合同", owner_id=roles.sales_a.id)
    session.add(contract)
    await session.commit()
    # 空内容文件 → DomainError → failed
    CONTRACT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (CONTRACT_UPLOAD_DIR / f"{contract.id}.txt").write_bytes(b"")

    maker = async_sessionmaker(engine, expire_on_commit=False)
    await process_contract_task({"sessionmaker": maker, "llm": llm}, str(contract.id))
    await session.refresh(contract)
    assert contract.status == ContractStatus.FAILED
    assert contract.error_msg is not None and "为空" in contract.error_msg

    headers = await login("sales_a@test.cn")
    resp = await client.post(f"/api/v1/contracts/{contract.id}/reprocess", headers=headers)
    assert resp.status_code == 202
    assert enqueued[-1] == ("process_contract_task", (str(contract.id),))
    await session.refresh(contract)
    assert contract.status == ContractStatus.PROCESSING


async def test_generate_draft_docx(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    account = Account(name="杭州云帆科技", industry="互联网", owner_id=roles.sales_a.id)
    session.add(account)
    await session.flush()
    opp = Opportunity(
        account_id=account.id,
        name="CRM 采购",
        amount=Decimal("150000"),
        stage=OpportunityStage.NEGOTIATION,
        owner_id=roles.sales_a.id,
    )
    session.add(opp)
    await session.commit()

    headers = await login("sales_a@test.cn")
    resp = await client.post(
        "/api/v1/contracts/generate",
        json={"opportunity_id": str(opp.id), "payment_terms": "签署后一次性支付全款"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.content[:2] == b"PK"  # docx = zip

    from docx import Document

    doc = Document(io.BytesIO(resp.content))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "杭州云帆科技" in text
    assert "150,000.00" in text
    assert "签署后一次性支付全款" in text
    assert "法务审核" in text  # 免责声明

    # RBAC：跨团队销售不能用别人的商机生成
    headers_b = await login("sales_b@test.cn")
    resp = await client.post(
        "/api/v1/contracts/generate", json={"opportunity_id": str(opp.id)}, headers=headers_b
    )
    assert resp.status_code == 404


async def test_reprocess_missing_file_rejected(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    contract = Contract(name="无文件合同", owner_id=roles.sales_a.id, status=ContractStatus.FAILED)
    session.add(contract)
    await session.commit()
    # 确保没有残留文件
    for suffix in (".txt", ".md", ".docx"):
        (CONTRACT_UPLOAD_DIR / f"{contract.id}{suffix}").unlink(missing_ok=True)

    headers = await login("sales_a@test.cn")
    resp = await client.post(f"/api/v1/contracts/{contract.id}/reprocess", headers=headers)
    assert resp.status_code == 400
    assert "源文件缺失" in resp.json()["message"]
