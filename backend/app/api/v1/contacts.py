import uuid

from fastapi import APIRouter

from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.schemas.contact import ContactCreate, ContactOut, ContactUpdate
from app.services import account_service

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.post("", status_code=201, summary="创建联系人")
async def create_contact(
    body: ContactCreate, session: SessionDep, current_user: CurrentUserDep
) -> ContactOut:
    contact = await account_service.create_contact(session, current_user, body)
    return ContactOut.model_validate(contact)


@router.patch("/{contact_id}", summary="更新联系人")
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> ContactOut:
    contact = await account_service.update_contact(session, current_user, contact_id, body)
    return ContactOut.model_validate(contact)


@router.delete("/{contact_id}", status_code=204, summary="删除联系人（软删）")
async def delete_contact(
    contact_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> None:
    await account_service.delete_contact(session, current_user, contact_id)
