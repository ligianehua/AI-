import urllib.parse
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select

from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.models.contract import Contract
from app.models.enums import ContractStatus
from app.models.user import User
from app.schemas.common import PageResult
from app.schemas.contract import ContractOut, GenerateDraftRequest
from app.services import contract_service

router = APIRouter(prefix="/contracts", tags=["contracts"])

PageParam = Annotated[int, Query(ge=1)]
PageSizeParam = Annotated[int, Query(ge=1, le=100)]


def _out(c: Contract, owner_name: str) -> ContractOut:
    return ContractOut(
        id=c.id,
        name=c.name,
        status=ContractStatus(c.status),
        opportunity_id=c.opportunity_id,
        extracted=c.extracted,
        review=c.review,
        error_msg=c.error_msg,
        owner_name=owner_name,
        created_at=c.created_at,
    )


@router.post("/upload", status_code=201, summary="上传合同（异步抽取要素+风险审查）")
async def upload_contract(
    file: UploadFile, session: SessionDep, current_user: CurrentUserDep
) -> ContractOut:
    content = await file.read()
    contract = await contract_service.upload_contract(
        session, current_user, file.filename or "合同", content
    )
    return _out(contract, current_user.name)


@router.get("", summary="合同列表（RBAC）")
async def list_contracts(
    session: SessionDep,
    current_user: CurrentUserDep,
    page: PageParam = 1,
    page_size: PageSizeParam = 20,
) -> PageResult[ContractOut]:
    items, total = await contract_service.contract_service.list(
        session, current_user, page=page, page_size=page_size
    )
    rows = (
        await session.execute(
            select(User.id, User.name).where(User.id.in_({c.owner_id for c in items}))
        )
    ).all()
    owner_names: dict[uuid.UUID, str] = {user_id: name for user_id, name in rows}
    return PageResult(
        items=[_out(c, owner_names.get(c.owner_id, "")) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{contract_id}", summary="合同详情（抽取要素 + 风险审查）")
async def get_contract(
    contract_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> ContractOut:
    contract = await contract_service.contract_service.get(session, current_user, contract_id)
    owner_name = await session.scalar(select(User.name).where(User.id == contract.owner_id))
    return _out(contract, owner_name or "")


@router.post("/{contract_id}/reprocess", status_code=202, summary="失败重试")
async def reprocess_contract(
    contract_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> dict[str, str]:
    await contract_service.reprocess_contract(session, current_user, contract_id)
    return {"message": "已重新提交处理"}


@router.delete("/{contract_id}", status_code=204, summary="删除合同（软删）")
async def delete_contract(
    contract_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> None:
    await contract_service.delete_contract(session, current_user, contract_id)


@router.post("/generate", summary="从商机生成标准合同草稿（docx 下载）")
async def generate_draft(
    body: GenerateDraftRequest, session: SessionDep, current_user: CurrentUserDep
) -> Response:
    filename, content = await contract_service.generate_draft_docx(
        session, current_user, body.opportunity_id, body.payment_terms
    )
    quoted = urllib.parse.quote(filename)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )
