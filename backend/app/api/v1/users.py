import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.schemas.common import PageResult
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])

PageParam = Annotated[int, Query(ge=1)]
PageSizeParam = Annotated[int, Query(ge=1, le=100)]


@router.get("", summary="用户列表（admin）")
async def list_users(
    session: SessionDep,
    current_user: CurrentUserDep,
    page: PageParam = 1,
    page_size: PageSizeParam = 20,
) -> PageResult[UserOut]:
    users, total = await user_service.list_users(session, current_user, page, page_size)
    return PageResult(
        items=[UserOut.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", status_code=201, summary="创建用户（admin）")
async def create_user(
    body: UserCreate, session: SessionDep, current_user: CurrentUserDep
) -> UserOut:
    user = await user_service.create_user(session, current_user, body)
    return UserOut.model_validate(user)


@router.get("/assignable", summary="可分配的负责人列表（manager=本团队 / admin=全部）")
async def list_assignable(session: SessionDep, current_user: CurrentUserDep) -> list[UserOut]:
    users = await user_service.list_assignable_users(session, current_user)
    return [UserOut.model_validate(u) for u in users]


@router.get("/{user_id}", summary="用户详情（admin）")
async def get_user(
    user_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> UserOut:
    user = await user_service.get_user(session, current_user, user_id)
    return UserOut.model_validate(user)


@router.patch("/{user_id}", summary="更新用户（admin）")
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, session: SessionDep, current_user: CurrentUserDep
) -> UserOut:
    user = await user_service.update_user(session, current_user, user_id, body)
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=204, summary="删除用户（admin，软删）")
async def delete_user(
    user_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> None:
    await user_service.delete_user(session, current_user, user_id)
