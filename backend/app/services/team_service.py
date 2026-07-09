"""团队管理（admin 专属）。RBAC 在本层强制。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.models.team import Team
from app.models.user import User
from app.schemas.team import TeamCreate, TeamUpdate
from app.services.user_service import require_admin


async def list_teams(
    session: AsyncSession, actor: User, page: int = 1, page_size: int = 20
) -> tuple[list[Team], int]:
    require_admin(actor)
    base = select(Team).where(Team.deleted_at.is_(None))
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    teams = await session.scalars(
        base.order_by(Team.created_at.asc()).limit(page_size).offset((page - 1) * page_size)
    )
    return list(teams), int(total or 0)


async def create_team(session: AsyncSession, actor: User, payload: TeamCreate) -> Team:
    require_admin(actor)
    existing = await session.scalar(
        select(Team).where(Team.name == payload.name, Team.deleted_at.is_(None))
    )
    if existing is not None:
        raise ConflictError("团队名已存在")
    team = Team(name=payload.name)
    session.add(team)
    await session.commit()
    await session.refresh(team)
    return team


async def get_team(session: AsyncSession, actor: User, team_id: uuid.UUID) -> Team:
    require_admin(actor)
    team = await session.scalar(select(Team).where(Team.id == team_id, Team.deleted_at.is_(None)))
    if team is None:
        raise NotFoundError("团队不存在")
    return team


async def update_team(
    session: AsyncSession, actor: User, team_id: uuid.UUID, payload: TeamUpdate
) -> Team:
    team = await get_team(session, actor, team_id)
    team.name = payload.name
    await session.commit()
    await session.refresh(team)
    return team


async def delete_team(session: AsyncSession, actor: User, team_id: uuid.UUID) -> None:
    team = await get_team(session, actor, team_id)
    member_count = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.team_id == team_id, User.deleted_at.is_(None))
    )
    if member_count:
        raise DomainError("团队下仍有成员，请先移出成员")
    team.deleted_at = datetime.now(UTC)
    await session.commit()
