import uuid

from fastapi import APIRouter

from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.models.enums import ActivityRelatedType
from app.schemas.activity import ActivityCreate, ActivityOut, ActivityUpdate
from app.services import activity_service

router = APIRouter(prefix="/activities", tags=["activities"])


@router.post("", status_code=201, summary="添加跟进记录（线索跟进会自动触发评分重算）")
async def create_activity(
    body: ActivityCreate, session: SessionDep, current_user: CurrentUserDep
) -> ActivityOut:
    activity = await activity_service.create_activity(session, current_user, body)
    out = ActivityOut.model_validate(activity)
    out.owner_name = current_user.name
    return out


@router.get("", summary="某实体的跟进记录列表")
async def list_activities(
    related_type: ActivityRelatedType,
    related_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> list[ActivityOut]:
    rows = await activity_service.list_activities(session, current_user, related_type, related_id)
    items = []
    for activity, owner_name in rows:
        out = ActivityOut.model_validate(activity)
        out.owner_name = owner_name
        items.append(out)
    return items


@router.patch("/{activity_id}", summary="更新跟进记录（仅本人）")
async def update_activity(
    activity_id: uuid.UUID,
    body: ActivityUpdate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> ActivityOut:
    activity = await activity_service.update_activity(session, current_user, activity_id, body)
    return ActivityOut.model_validate(activity)


@router.delete("/{activity_id}", status_code=204, summary="删除跟进记录（仅本人，软删）")
async def delete_activity(
    activity_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> None:
    await activity_service.delete_activity(session, current_user, activity_id)
