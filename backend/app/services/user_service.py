"""用户管理（admin 专属）。RBAC 在本层强制。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    DomainError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.security import hash_password
from app.models.enums import Role
from app.models.team import Team
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


def require_admin(actor: User) -> None:
    if actor.role != Role.ADMIN:
        raise PermissionDeniedError("仅管理员可执行此操作")


async def _ensure_team_exists(session: AsyncSession, team_id: uuid.UUID | None) -> None:
    if team_id is None:
        return
    team = await session.scalar(select(Team).where(Team.id == team_id, Team.deleted_at.is_(None)))
    if team is None:
        raise DomainError("团队不存在")


async def list_assignable_users(session: AsyncSession, actor: User) -> list[User]:
    """可分配对象：manager=本团队成员，admin=全部在职用户；sales 禁止。"""
    if actor.role == Role.SALES:
        raise PermissionDeniedError("销售不能分配线索")
    stmt = select(User).where(User.deleted_at.is_(None), User.is_active)
    if actor.role == Role.MANAGER:
        stmt = stmt.where(User.team_id == actor.team_id)
    return list(await session.scalars(stmt.order_by(User.name.asc())))


async def list_users(
    session: AsyncSession, actor: User, page: int = 1, page_size: int = 20
) -> tuple[list[User], int]:
    require_admin(actor)
    base = select(User).where(User.deleted_at.is_(None))
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    users = await session.scalars(
        base.order_by(User.created_at.asc()).limit(page_size).offset((page - 1) * page_size)
    )
    return list(users), int(total or 0)


async def create_user(session: AsyncSession, actor: User, payload: UserCreate) -> User:
    require_admin(actor)
    existing = await session.scalar(
        select(User).where(User.email == payload.email, User.deleted_at.is_(None))
    )
    if existing is not None:
        raise ConflictError("邮箱已被使用")
    await _ensure_team_exists(session, payload.team_id)
    user = User(
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role.value,
        team_id=payload.team_id,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_user(session: AsyncSession, actor: User, user_id: uuid.UUID) -> User:
    require_admin(actor)
    user = await session.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise NotFoundError("用户不存在")
    return user


async def update_user(
    session: AsyncSession, actor: User, user_id: uuid.UUID, payload: UserUpdate
) -> User:
    user = await get_user(session, actor, user_id)
    data = payload.model_dump(exclude_unset=True)
    if "team_id" in data:
        await _ensure_team_exists(session, data["team_id"])
    password = data.pop("password", None)
    if password:
        user.hashed_password = hash_password(password)
    for key, value in data.items():
        setattr(user, key, value)
    await session.commit()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, actor: User, user_id: uuid.UUID) -> None:
    if user_id == actor.id:
        raise DomainError("不能删除当前登录账号")
    user = await get_user(session, actor, user_id)
    user.deleted_at = datetime.now(UTC)
    user.is_active = False
    await session.commit()
