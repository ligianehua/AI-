"""跟进记录：多态挂载 lead/account/opportunity，权限跟随宿主实体可见域。

线索新增跟进后自动触发评分重算（PLAN §6.1 触发时机）。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.activity import Activity
from app.models.enums import ActivityRelatedType, Role
from app.models.lead import Lead
from app.models.user import User
from app.schemas.activity import ActivityCreate, ActivityUpdate
from app.services.account_service import account_service
from app.services.base import BaseService
from app.services.lead_service import lead_service
from app.services.opportunity_service import opportunity_service
from app.tasks import dispatcher


class _LeadScope(BaseService[Lead]):
    model = Lead


async def _check_related_access(
    session: AsyncSession, actor: User, related_type: ActivityRelatedType, related_id: uuid.UUID
) -> None:
    """宿主实体必须存在且在可见域内（否则 404 不泄露存在性）。"""
    if related_type == ActivityRelatedType.LEAD:
        await lead_service.get(session, actor, related_id)
    elif related_type == ActivityRelatedType.ACCOUNT:
        await account_service.get(session, actor, related_id)
    else:
        await opportunity_service.get(session, actor, related_id)


async def create_activity(session: AsyncSession, actor: User, payload: ActivityCreate) -> Activity:
    await _check_related_access(session, actor, payload.related_type, payload.related_id)
    activity = Activity(**payload.model_dump(), owner_id=actor.id)
    session.add(activity)
    await session.commit()
    await session.refresh(activity)
    if payload.related_type == ActivityRelatedType.LEAD:
        # 线索新增跟进 → 自动重算评分
        await dispatcher.enqueue("score_lead_task", str(payload.related_id))
    return activity


async def list_activities(
    session: AsyncSession, actor: User, related_type: ActivityRelatedType, related_id: uuid.UUID
) -> list[tuple[Activity, str]]:
    await _check_related_access(session, actor, related_type, related_id)
    rows = (
        await session.execute(
            select(Activity, User.name)
            .join(User, User.id == Activity.owner_id)
            .where(
                Activity.related_type == related_type,
                Activity.related_id == related_id,
                Activity.deleted_at.is_(None),
            )
            .order_by(Activity.created_at.desc())
        )
    ).all()
    return [(activity, owner_name) for activity, owner_name in rows]


async def _get_own_activity(session: AsyncSession, actor: User, activity_id: uuid.UUID) -> Activity:
    activity = await session.scalar(
        select(Activity).where(Activity.id == activity_id, Activity.deleted_at.is_(None))
    )
    if activity is None:
        raise NotFoundError("跟进记录不存在")
    if actor.role != Role.ADMIN and activity.owner_id != actor.id:
        raise PermissionDeniedError("只能操作自己的跟进记录")
    # 宿主实体也必须仍在可见域内（如被调离团队后，不能再改原团队商机下的记录）
    await _check_related_access(
        session, actor, ActivityRelatedType(activity.related_type), activity.related_id
    )
    return activity


async def update_activity(
    session: AsyncSession, actor: User, activity_id: uuid.UUID, payload: ActivityUpdate
) -> Activity:
    activity = await _get_own_activity(session, actor, activity_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(activity, key, value)
    await session.commit()
    await session.refresh(activity)
    return activity


async def delete_activity(session: AsyncSession, actor: User, activity_id: uuid.UUID) -> None:
    activity = await _get_own_activity(session, actor, activity_id)
    activity.deleted_at = datetime.now(UTC)
    await session.commit()
