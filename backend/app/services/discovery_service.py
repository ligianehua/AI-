"""M8 线索发现：订阅 CRUD / 抓取入池 / 领取转线索。RBAC 在本层强制。"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, DomainError
from app.models.account import Account
from app.models.discovery_candidate import DiscoveryCandidate
from app.models.discovery_subscription import DiscoverySubscription
from app.models.enums import CandidateStatus, LeadSource, LeadStatus
from app.models.lead import Lead
from app.models.user import User
from app.schemas.discovery import SubscriptionCreate, SubscriptionUpdate
from app.schemas.lead import DuplicateWarning
from app.services.base import BaseService
from app.services.google_places import PlaceResult
from app.services.lead_service import find_duplicates
from app.tasks import dispatcher

logger = logging.getLogger(__name__)


class SubscriptionService(BaseService[DiscoverySubscription]):
    model = DiscoverySubscription
    sortable_fields = frozenset({"created_at", "last_run_at", "name"})


class CandidateService(BaseService[DiscoveryCandidate]):
    model = DiscoveryCandidate
    sortable_fields = frozenset({"created_at", "name", "status"})


subscription_service = SubscriptionService()
candidate_service = CandidateService()


# ---------- 订阅 ----------


async def create_subscription(
    session: AsyncSession, actor: User, payload: SubscriptionCreate
) -> DiscoverySubscription:
    sub = DiscoverySubscription(
        name=payload.name or f"{payload.city} {payload.category}",
        country=payload.country,
        city=payload.city,
        category=payload.category,
        keyword=payload.keyword,
        owner_id=actor.id,
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


async def update_subscription(
    session: AsyncSession, actor: User, sub_id: uuid.UUID, payload: SubscriptionUpdate
) -> DiscoverySubscription:
    sub = await subscription_service.get(session, actor, sub_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(sub, key, value)
    await session.commit()
    await session.refresh(sub)
    return sub


async def delete_subscription(session: AsyncSession, actor: User, sub_id: uuid.UUID) -> None:
    sub = await subscription_service.get(session, actor, sub_id)
    sub.deleted_at = datetime.now(UTC)
    await session.commit()


async def trigger_run(session: AsyncSession, actor: User, sub_id: uuid.UUID) -> bool:
    """手动触发抓取（异步任务）。返回是否成功入队。"""
    sub = await subscription_service.get(session, actor, sub_id)
    if not sub.is_active:
        raise DomainError("订阅已停用，请先启用再抓取")
    # key 缺失在提交前同步拦下，给用户可读错误（任务里只能进日志）
    if not get_settings().google_maps_api_key:
        raise DomainError("未配置 GOOGLE_MAPS_API_KEY，线索发现不可用（见 .env.example）")
    return await dispatcher.enqueue("run_discovery_task", str(sub.id))


def build_query(sub: DiscoverySubscription) -> str:
    base = f"{sub.category} in {sub.city}, {sub.country}"
    return f"{sub.keyword} {base}" if sub.keyword else base


# ---------- 抓取入池 ----------


async def ingest_places(
    session: AsyncSession, sub: DiscoverySubscription, places: list[PlaceResult]
) -> int:
    """抓取结果入候选池：place_id 幂等去重 + 库内撞单提示（不拦截）。返回新增数。"""
    new_count = 0
    if places:
        existing_ids = set(
            await session.scalars(
                select(DiscoveryCandidate.place_id).where(
                    DiscoveryCandidate.place_id.in_([p.place_id for p in places]),
                    DiscoveryCandidate.deleted_at.is_(None),
                )
            )
        )
        fresh = [p for p in places if p.place_id not in existing_ids]

        names = {p.name for p in fresh}
        phones = {p.phone for p in fresh if p.phone}
        dup_lead_names: set[str] = set()
        dup_lead_phones: set[str] = set()
        dup_account_names: set[str] = set()
        if names:
            dup_lead_names = set(
                await session.scalars(
                    select(Lead.account_name).where(
                        Lead.account_name.in_(names), Lead.deleted_at.is_(None)
                    )
                )
            )
            dup_account_names = set(
                await session.scalars(
                    select(Account.name).where(
                        Account.name.in_(names), Account.deleted_at.is_(None)
                    )
                )
            )
        if phones:
            dup_lead_phones = {
                p
                for p in await session.scalars(
                    select(Lead.contact_phone).where(
                        Lead.contact_phone.in_(phones), Lead.deleted_at.is_(None)
                    )
                )
                if p
            }

        for p in fresh:
            hint = None
            if p.phone and p.phone in dup_lead_phones:
                hint = f"疑似撞单：库内已有同电话线索（{p.phone}）"
            elif p.name in dup_lead_names:
                hint = f"疑似撞单：库内已有同名线索（{p.name}）"
            elif p.name in dup_account_names:
                hint = f"疑似撞单：库内已有同名客户（{p.name}）"
            session.add(
                DiscoveryCandidate(
                    subscription_id=sub.id,
                    place_id=p.place_id,
                    name=p.name[:300],
                    address=p.address,
                    phone=p.phone,
                    website=p.website[:500] if p.website else None,
                    country=sub.country,
                    city=sub.city,
                    category=sub.category,
                    duplicate_hint=hint,
                    owner_id=sub.owner_id,
                    raw=p.raw,
                )
            )
            new_count += 1

    sub.last_run_at = datetime.now(UTC)
    sub.last_run_new = new_count
    await session.commit()
    return new_count


# ---------- 候选池 ----------


async def list_candidates(
    session: AsyncSession,
    actor: User,
    *,
    status: CandidateStatus | None = None,
    subscription_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[DiscoveryCandidate], int]:
    stmt = candidate_service.base_query(actor)
    if status is not None:
        stmt = stmt.where(DiscoveryCandidate.status == status)
    if subscription_id is not None:
        stmt = stmt.where(DiscoveryCandidate.subscription_id == subscription_id)
    stmt = stmt.order_by(DiscoveryCandidate.created_at.desc())
    return await candidate_service.paginate(session, stmt, page, page_size)


async def claim_candidate(
    session: AsyncSession, actor: User, candidate_id: uuid.UUID
) -> tuple[Lead, list[DuplicateWarning]]:
    """领取：事务内创建线索（source=discovery）+ 候选置 claimed + 触发评分。

    行锁防并发双击：后到者看到非 pending 状态被 409。
    """
    candidate = await candidate_service.get(session, actor, candidate_id)
    candidate = await session.scalar(  # type: ignore[assignment]
        select(DiscoveryCandidate).where(DiscoveryCandidate.id == candidate.id).with_for_update()
    )
    assert candidate is not None
    if candidate.status != CandidateStatus.PENDING:
        raise ConflictError("该候选已被领取或已忽略")

    desc_parts = [
        f"来自线索发现（{candidate.city}, {candidate.country}），品类：{candidate.category}"
    ]
    if candidate.address:
        desc_parts.append(f"地址：{candidate.address}")
    if candidate.website:
        desc_parts.append(f"网站：{candidate.website}")
    lead = Lead(
        source=LeadSource.DISCOVERY,
        account_name=candidate.name[:200],
        contact_phone=candidate.phone[:30] if candidate.phone else None,
        industry=candidate.category[:50],
        requirement_desc="；".join(desc_parts),
        status=LeadStatus.NEW,
        owner_id=candidate.owner_id,
    )
    session.add(lead)
    await session.flush()
    candidate.status = CandidateStatus.CLAIMED
    candidate.claimed_lead_id = lead.id
    await session.commit()
    await session.refresh(lead)

    warnings = await find_duplicates(
        session, lead.contact_phone, lead.account_name, exclude_id=lead.id
    )
    await dispatcher.enqueue("score_lead_task", str(lead.id))
    return lead, warnings


async def ignore_candidate(
    session: AsyncSession, actor: User, candidate_id: uuid.UUID
) -> DiscoveryCandidate:
    candidate = await candidate_service.get(session, actor, candidate_id)
    if candidate.status == CandidateStatus.CLAIMED:
        raise ConflictError("已领取的候选不能忽略")
    candidate.status = CandidateStatus.IGNORED
    await session.commit()
    await session.refresh(candidate)
    return candidate
