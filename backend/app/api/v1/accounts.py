import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.schemas.account import (
    AccountCreate,
    AccountDetail,
    AccountOut,
    AccountUpdate,
    TimelineItem,
)
from app.schemas.common import PageResult
from app.schemas.contact import ContactOut
from app.services import account_service

router = APIRouter(prefix="/accounts", tags=["accounts"])

PageParam = Annotated[int, Query(ge=1)]
PageSizeParam = Annotated[int, Query(ge=1, le=100)]


@router.post("", status_code=201, summary="创建客户")
async def create_account(
    body: AccountCreate, session: SessionDep, current_user: CurrentUserDep
) -> AccountOut:
    account = await account_service.create_account(session, current_user, body)
    return AccountOut.model_validate(account)


@router.get("", summary="客户列表（q 按名称模糊搜索）")
async def list_accounts(
    session: SessionDep,
    current_user: CurrentUserDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sort: str | None = None,
    page: PageParam = 1,
    page_size: PageSizeParam = 20,
) -> PageResult[AccountOut]:
    rows, total = await account_service.list_accounts(
        session, current_user, q=q, page=page, page_size=page_size, sort=sort
    )
    items = []
    for account, owner_name in rows:
        out = AccountOut.model_validate(account)
        out.owner_name = owner_name
        items.append(out)
    return PageResult(items=items, total=total, page=page, page_size=page_size)


@router.get("/{account_id}", summary="客户 360 详情（含联系人）")
async def get_account(
    account_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> AccountDetail:
    account, owner_name, contacts = await account_service.get_account_with_contacts(
        session, current_user, account_id
    )
    detail = AccountDetail.model_validate(account)
    detail.owner_name = owner_name
    detail.contacts = [ContactOut.model_validate(c) for c in contacts]
    return detail


@router.patch("/{account_id}", summary="更新客户")
async def update_account(
    account_id: uuid.UUID,
    body: AccountUpdate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> AccountOut:
    account = await account_service.update_account(session, current_user, account_id, body)
    return AccountOut.model_validate(account)


@router.get("/{account_id}/timeline", summary="跟进时间线（聚合线索/客户/商机）")
async def get_timeline(
    account_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> list[TimelineItem]:
    return await account_service.get_timeline(session, current_user, account_id)


@router.post("/{account_id}/profile", status_code=202, summary="生成/刷新 AI 画像（异步）")
async def refresh_profile(
    account_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> dict[str, str]:
    await account_service.trigger_profile(session, current_user, account_id)
    return {"message": "画像生成任务已提交，请稍后刷新查看"}
