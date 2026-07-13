import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.models.discovery_candidate import DiscoveryCandidate
from app.models.discovery_subscription import DiscoverySubscription
from app.models.enums import CandidateStatus
from app.models.user import User
from app.schemas.common import PageResult
from app.schemas.discovery import (
    CandidateOut,
    ClaimResult,
    RunResult,
    SubscriptionCreate,
    SubscriptionOut,
    SubscriptionUpdate,
)
from app.services import discovery_service

router = APIRouter(prefix="/discovery", tags=["discovery"])

PageParam = Annotated[int, Query(ge=1)]
PageSizeParam = Annotated[int, Query(ge=1, le=100)]


def _sub_out(sub: DiscoverySubscription, owner_name: str) -> SubscriptionOut:
    return SubscriptionOut(
        id=sub.id,
        name=sub.name,
        country=sub.country,
        city=sub.city,
        category=sub.category,
        keyword=sub.keyword,
        is_active=sub.is_active,
        owner_name=owner_name,
        last_run_at=sub.last_run_at,
        last_run_new=sub.last_run_new,
        created_at=sub.created_at,
    )


def _candidate_out(c: DiscoveryCandidate) -> CandidateOut:
    return CandidateOut(
        id=c.id,
        subscription_id=c.subscription_id,
        name=c.name,
        address=c.address,
        phone=c.phone,
        website=c.website,
        country=c.country,
        city=c.city,
        category=c.category,
        status=CandidateStatus(c.status),
        duplicate_hint=c.duplicate_hint,
        claimed_lead_id=c.claimed_lead_id,
        created_at=c.created_at,
    )


@router.post("/subscriptions", status_code=201, summary="创建抓取订阅")
async def create_subscription(
    body: SubscriptionCreate, session: SessionDep, current_user: CurrentUserDep
) -> SubscriptionOut:
    sub = await discovery_service.create_subscription(session, current_user, body)
    return _sub_out(sub, current_user.name)


@router.get("/subscriptions", summary="订阅列表（RBAC）")
async def list_subscriptions(
    session: SessionDep,
    current_user: CurrentUserDep,
    page: PageParam = 1,
    page_size: PageSizeParam = 20,
) -> PageResult[SubscriptionOut]:
    items, total = await discovery_service.subscription_service.list(
        session, current_user, page=page, page_size=page_size
    )
    rows = (
        await session.execute(
            select(User.id, User.name).where(User.id.in_({s.owner_id for s in items}))
        )
    ).all()
    owner_names: dict[uuid.UUID, str] = {user_id: name for user_id, name in rows}
    return PageResult(
        items=[_sub_out(s, owner_names.get(s.owner_id, "")) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/subscriptions/{sub_id}", summary="更新订阅（启停/改条件）")
async def update_subscription(
    sub_id: uuid.UUID,
    body: SubscriptionUpdate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> SubscriptionOut:
    sub = await discovery_service.update_subscription(session, current_user, sub_id, body)
    owner_name = await session.scalar(select(User.name).where(User.id == sub.owner_id))
    return _sub_out(sub, owner_name or "")


@router.delete("/subscriptions/{sub_id}", status_code=204, summary="删除订阅（软删）")
async def delete_subscription(
    sub_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> None:
    await discovery_service.delete_subscription(session, current_user, sub_id)


@router.post("/subscriptions/{sub_id}/run", status_code=202, summary="手动抓取（异步）")
async def run_subscription(
    sub_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> RunResult:
    enqueued = await discovery_service.trigger_run(session, current_user, sub_id)
    return RunResult(
        enqueued=enqueued,
        message="抓取任务已提交，稍后刷新候选池" if enqueued else "任务提交失败，请稍后重试",
    )


@router.get("/candidates", summary="候选池列表（RBAC）")
async def list_candidates(
    session: SessionDep,
    current_user: CurrentUserDep,
    status: CandidateStatus | None = None,
    subscription_id: uuid.UUID | None = None,
    page: PageParam = 1,
    page_size: PageSizeParam = 20,
) -> PageResult[CandidateOut]:
    items, total = await discovery_service.list_candidates(
        session,
        current_user,
        status=status,
        subscription_id=subscription_id,
        page=page,
        page_size=page_size,
    )
    return PageResult(
        items=[_candidate_out(c) for c in items], total=total, page=page, page_size=page_size
    )


@router.post("/candidates/{candidate_id}/claim", summary="领取 → 创建线索并自动评分")
async def claim_candidate(
    candidate_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> ClaimResult:
    lead, warnings = await discovery_service.claim_candidate(session, current_user, candidate_id)
    return ClaimResult(lead_id=lead.id, duplicate_warnings=warnings)


@router.post("/candidates/{candidate_id}/ignore", summary="忽略候选")
async def ignore_candidate(
    candidate_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> CandidateOut:
    candidate = await discovery_service.ignore_candidate(session, current_user, candidate_id)
    return _candidate_out(candidate)
