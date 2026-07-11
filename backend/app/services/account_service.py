"""客户业务逻辑：CRUD / 联系人 / 时间线聚合。RBAC 在本层强制。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.account import Account
from app.models.activity import Activity
from app.models.contact import Contact
from app.models.enums import ActivityRelatedType
from app.models.lead import Lead
from app.models.opportunity import Opportunity
from app.models.user import User
from app.schemas.account import AccountCreate, AccountUpdate, TimelineItem
from app.schemas.contact import ContactCreate, ContactUpdate
from app.services.base import BaseService
from app.tasks import dispatcher


class AccountService(BaseService[Account]):
    model = Account
    sortable_fields = frozenset({"created_at", "name"})


account_service = AccountService()


async def create_account(session: AsyncSession, actor: User, payload: AccountCreate) -> Account:
    account = Account(**payload.model_dump(), owner_id=actor.id)
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


async def list_accounts(
    session: AsyncSession,
    actor: User,
    *,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
    sort: str | None = None,
) -> tuple[list[tuple[Account, str]], int]:
    """返回 [(account, owner_name)], total。q 按名称模糊搜。"""
    stmt = account_service.base_query(actor)
    if q:
        stmt = stmt.where(Account.name.ilike(f"%{q}%"))
    total = int(
        await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    )
    sorted_stmt = account_service.apply_sort(stmt, sort)
    rows = (
        await session.execute(
            sorted_stmt.add_columns(User.name)
            .join(User, User.id == Account.owner_id)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()
    return [(account, owner_name) for account, owner_name in rows], total


async def get_account_with_contacts(
    session: AsyncSession, actor: User, account_id: uuid.UUID
) -> tuple[Account, str, list[Contact]]:
    account = await account_service.get(session, actor, account_id)
    owner_name = await session.scalar(select(User.name).where(User.id == account.owner_id))
    contacts = list(
        await session.scalars(
            select(Contact)
            .where(Contact.account_id == account.id, Contact.deleted_at.is_(None))
            .order_by(Contact.created_at.asc())
        )
    )
    return account, owner_name or "", contacts


async def update_account(
    session: AsyncSession, actor: User, account_id: uuid.UUID, payload: AccountUpdate
) -> Account:
    account = await account_service.get(session, actor, account_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, key, value)
    await session.commit()
    await session.refresh(account)
    return account


async def get_timeline(
    session: AsyncSession, actor: User, account_id: uuid.UUID
) -> list[TimelineItem]:
    """时间线聚合：客户直挂 + 转化前线索 + 名下商机 的全部跟进记录。"""
    account = await account_service.get(session, actor, account_id)

    lead_rows = (
        await session.execute(
            select(Lead.id, Lead.account_name).where(
                Lead.converted_account_id == account.id, Lead.deleted_at.is_(None)
            )
        )
    ).all()
    opp_rows = (
        await session.execute(
            select(Opportunity.id, Opportunity.name).where(
                Opportunity.account_id == account.id, Opportunity.deleted_at.is_(None)
            )
        )
    ).all()
    lead_names = {row[0]: row[1] for row in lead_rows}
    opp_names = {row[0]: row[1] for row in opp_rows}

    conditions = [
        and_(
            Activity.related_type == ActivityRelatedType.ACCOUNT,
            Activity.related_id == account.id,
        )
    ]
    if lead_names:
        conditions.append(
            and_(
                Activity.related_type == ActivityRelatedType.LEAD,
                Activity.related_id.in_(lead_names.keys()),
            )
        )
    if opp_names:
        conditions.append(
            and_(
                Activity.related_type == ActivityRelatedType.OPPORTUNITY,
                Activity.related_id.in_(opp_names.keys()),
            )
        )

    rows = (
        await session.execute(
            select(Activity, User.name)
            .join(User, User.id == Activity.owner_id)
            .where(Activity.deleted_at.is_(None), or_(*conditions))
            .order_by(Activity.created_at.desc())
        )
    ).all()

    items: list[TimelineItem] = []
    for activity, owner_name in rows:
        related_type = ActivityRelatedType(activity.related_type)
        if related_type == ActivityRelatedType.LEAD:
            label = f"线索：{lead_names.get(activity.related_id, '')}"
        elif related_type == ActivityRelatedType.OPPORTUNITY:
            label = f"商机：{opp_names.get(activity.related_id, '')}"
        else:
            label = "客户跟进"
        items.append(
            TimelineItem(
                id=activity.id,
                related_type=related_type,
                related_label=label,
                type=activity.type,
                content=activity.content,
                next_action=activity.next_action,
                next_action_date=activity.next_action_date,
                owner_name=owner_name,
                created_at=activity.created_at,
            )
        )
    return items


async def trigger_profile(session: AsyncSession, actor: User, account_id: uuid.UUID) -> None:
    account = await account_service.get(session, actor, account_id)
    await dispatcher.enqueue("account_profile_task", str(account.id))


# ---------- 联系人 ----------


async def _account_for_contact_op(
    session: AsyncSession, actor: User, account_id: uuid.UUID
) -> Account:
    """联系人无 owner 字段，权限跟随所属客户的可见域。"""
    return await account_service.get(session, actor, account_id)


async def create_contact(session: AsyncSession, actor: User, payload: ContactCreate) -> Contact:
    await _account_for_contact_op(session, actor, payload.account_id)
    contact = Contact(**payload.model_dump())
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


async def get_contact(session: AsyncSession, actor: User, contact_id: uuid.UUID) -> Contact:
    contact = await session.scalar(
        select(Contact).where(Contact.id == contact_id, Contact.deleted_at.is_(None))
    )
    if contact is None:
        raise NotFoundError("联系人不存在")
    await _account_for_contact_op(session, actor, contact.account_id)
    return contact


async def update_contact(
    session: AsyncSession, actor: User, contact_id: uuid.UUID, payload: ContactUpdate
) -> Contact:
    contact = await get_contact(session, actor, contact_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(contact, key, value)
    await session.commit()
    await session.refresh(contact)
    return contact


async def delete_contact(session: AsyncSession, actor: User, contact_id: uuid.UUID) -> None:
    contact = await get_contact(session, actor, contact_id)
    contact.deleted_at = datetime.now(UTC)
    await session.commit()
