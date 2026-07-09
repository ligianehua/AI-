"""RBAC 可见域测试：sales=本人 / manager=本团队 / admin=全量。"""

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import Account, Lead, Opportunity, User
from app.models.enums import LeadSource, OpportunityStage
from app.services.base import BaseService
from tests.conftest import RoleUsers

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


class AccountService(BaseService[Account]):
    model = Account


def _account(name: str, owner: User) -> Account:
    return Account(name=name, owner_id=owner.id)


def _lead(owner: User) -> Lead:
    return Lead(
        source=LeadSource.REFERRAL,
        account_name=f"线索公司-{uuid.uuid4().hex[:6]}",
        owner_id=owner.id,
    )


def _opportunity(account: Account, owner: User, amount: int, stage: str) -> Opportunity:
    return Opportunity(
        account_id=account.id,
        name=f"商机-{uuid.uuid4().hex[:6]}",
        amount=Decimal(amount),
        stage=stage,
        owner_id=owner.id,
    )


@pytest.fixture
async def scoped_data(session: AsyncSession, roles: RoleUsers) -> dict[str, Account]:
    a1 = _account("A组销售一的客户1", roles.sales_a)
    a2 = _account("A组销售一的客户2", roles.sales_a)
    a3 = _account("A组销售二的客户", roles.sales_a2)
    b1 = _account("B组销售的客户", roles.sales_b)
    session.add_all([a1, a2, a3, b1])
    session.add_all([_lead(roles.sales_a), _lead(roles.sales_a), _lead(roles.sales_b)])
    await session.flush()
    session.add_all(
        [
            _opportunity(a1, roles.sales_a, 100_000, OpportunityStage.INITIAL),
            _opportunity(a3, roles.sales_a2, 200_000, OpportunityStage.PROPOSAL),
            _opportunity(b1, roles.sales_b, 400_000, OpportunityStage.NEGOTIATION),
            _opportunity(b1, roles.sales_b, 800_000, OpportunityStage.WON),  # 不计入在途
        ]
    )
    await session.commit()
    return {"a1": a1, "b1": b1}


async def test_sales_sees_only_own(
    session: AsyncSession, roles: RoleUsers, scoped_data: dict[str, Account]
) -> None:
    service = AccountService()
    items, total = await service.list(session, roles.sales_a)
    assert total == 2
    assert all(item.owner_id == roles.sales_a.id for item in items)


async def test_manager_sees_whole_team(
    session: AsyncSession, roles: RoleUsers, scoped_data: dict[str, Account]
) -> None:
    service = AccountService()
    _, total = await service.list(session, roles.manager_a)
    assert total == 3  # sales_a 的 2 个 + sales_a2 的 1 个，不含 B 组


async def test_admin_sees_all(
    session: AsyncSession, roles: RoleUsers, scoped_data: dict[str, Account]
) -> None:
    service = AccountService()
    _, total = await service.list(session, roles.admin)
    assert total == 4


async def test_sales_cannot_get_others_record(
    session: AsyncSession, roles: RoleUsers, scoped_data: dict[str, Account]
) -> None:
    service = AccountService()
    with pytest.raises(NotFoundError):
        await service.get(session, roles.sales_a, scoped_data["b1"].id)
    # 本人可以取到
    own = await service.get(session, roles.sales_a, scoped_data["a1"].id)
    assert own.name == "A组销售一的客户1"


async def test_dashboard_summary_scoped(
    client: AsyncClient,
    roles: RoleUsers,
    scoped_data: dict[str, Account],
    login: LoginFn,
) -> None:
    async def summary(email: str) -> dict[str, float]:
        headers = await login(email)
        resp = await client.get("/api/v1/dashboard/summary", headers=headers)
        assert resp.status_code == 200
        return dict(resp.json())

    sales_a = await summary("sales_a@test.cn")
    assert sales_a["account_count"] == 2
    assert sales_a["lead_count"] == 2
    assert sales_a["opportunity_count"] == 1
    assert sales_a["pipeline_amount"] == 100_000

    manager_a = await summary("manager_a@test.cn")
    assert manager_a["account_count"] == 3
    assert manager_a["opportunity_count"] == 2
    assert manager_a["pipeline_amount"] == 300_000

    admin = await summary("admin@test.cn")
    assert admin["account_count"] == 4
    assert admin["opportunity_count"] == 4
    # won 商机不计入在途金额
    assert admin["pipeline_amount"] == 700_000

    sales_b = await summary("sales_b@test.cn")
    assert sales_b["account_count"] == 1
    assert sales_b["pipeline_amount"] == 400_000
