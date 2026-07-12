import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.schemas.common import PageResult
from app.schemas.notification import NotificationOut, UnreadCountResponse
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])

PageParam = Annotated[int, Query(ge=1)]
PageSizeParam = Annotated[int, Query(ge=1, le=100)]


@router.get("", summary="风险提醒列表（仅本人）")
async def list_notifications(
    session: SessionDep,
    current_user: CurrentUserDep,
    unread_only: bool = False,
    page: PageParam = 1,
    page_size: PageSizeParam = 20,
) -> PageResult[NotificationOut]:
    items, total = await notification_service.list_notifications(
        session, current_user, unread_only=unread_only, page=page, page_size=page_size
    )
    return PageResult(
        items=[NotificationOut.model_validate(n) for n in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", summary="未读数（导航红点）")
async def get_unread_count(
    session: SessionDep, current_user: CurrentUserDep
) -> UnreadCountResponse:
    return UnreadCountResponse(
        unread=await notification_service.unread_count(session, current_user)
    )


@router.post("/{notification_id}/read", status_code=204, summary="标记已读")
async def mark_read(
    notification_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> None:
    await notification_service.mark_read(session, current_user, notification_id)


@router.post("/read-all", status_code=204, summary="全部标记已读")
async def mark_all_read(session: SessionDep, current_user: CurrentUserDep) -> None:
    await notification_service.mark_all_read(session, current_user)
