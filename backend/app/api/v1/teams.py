import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.schemas.common import PageResult
from app.schemas.team import TeamCreate, TeamOut, TeamUpdate
from app.services import team_service

router = APIRouter(prefix="/teams", tags=["teams"])

PageParam = Annotated[int, Query(ge=1)]
PageSizeParam = Annotated[int, Query(ge=1, le=100)]


@router.get("", summary="团队列表（admin）")
async def list_teams(
    session: SessionDep,
    current_user: CurrentUserDep,
    page: PageParam = 1,
    page_size: PageSizeParam = 20,
) -> PageResult[TeamOut]:
    teams, total = await team_service.list_teams(session, current_user, page, page_size)
    return PageResult(
        items=[TeamOut.model_validate(t) for t in teams],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", status_code=201, summary="创建团队（admin）")
async def create_team(
    body: TeamCreate, session: SessionDep, current_user: CurrentUserDep
) -> TeamOut:
    team = await team_service.create_team(session, current_user, body)
    return TeamOut.model_validate(team)


@router.get("/{team_id}", summary="团队详情（admin）")
async def get_team(
    team_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> TeamOut:
    team = await team_service.get_team(session, current_user, team_id)
    return TeamOut.model_validate(team)


@router.patch("/{team_id}", summary="更新团队（admin）")
async def update_team(
    team_id: uuid.UUID, body: TeamUpdate, session: SessionDep, current_user: CurrentUserDep
) -> TeamOut:
    team = await team_service.update_team(session, current_user, team_id, body)
    return TeamOut.model_validate(team)


@router.delete("/{team_id}", status_code=204, summary="删除团队（admin，软删）")
async def delete_team(
    team_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> None:
    await team_service.delete_team(session, current_user, team_id)
