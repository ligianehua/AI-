"""通知：只属于本人，无跨可见域概念。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.notification import Notification
from app.models.user import User


async def list_notifications(
    session: AsyncSession,
    actor: User,
    *,
    unread_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Notification], int]:
    stmt = select(Notification).where(
        Notification.user_id == actor.id, Notification.deleted_at.is_(None)
    )
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = await session.scalars(
        stmt.order_by(Notification.created_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    return list(rows), total


async def unread_count(session: AsyncSession, actor: User) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == actor.id,
                Notification.read_at.is_(None),
                Notification.deleted_at.is_(None),
            )
        )
        or 0
    )


async def mark_read(session: AsyncSession, actor: User, notification_id: uuid.UUID) -> None:
    notification = await session.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == actor.id,
            Notification.deleted_at.is_(None),
        )
    )
    if notification is None:
        raise NotFoundError("通知不存在")
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        await session.commit()


async def mark_all_read(session: AsyncSession, actor: User) -> int:
    rows = list(
        await session.scalars(
            select(Notification).where(
                Notification.user_id == actor.id,
                Notification.read_at.is_(None),
                Notification.deleted_at.is_(None),
            )
        )
    )
    now = datetime.now(UTC)
    for n in rows:
        n.read_at = now
    await session.commit()
    return len(rows)
