import uuid
from typing import Annotated

from fastapi import APIRouter, Query, UploadFile
from fastapi.responses import Response

from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.models.enums import LeadStatus
from app.schemas.activity import ActivityOut
from app.schemas.common import PageResult
from app.schemas.lead import (
    AssignRequest,
    AssignResult,
    ConvertRequest,
    ConvertResult,
    LeadCreate,
    LeadCreateResult,
    LeadDetail,
    LeadImportReport,
    LeadOut,
    LeadUpdate,
)
from app.services import lead_service

router = APIRouter(prefix="/leads", tags=["leads"])

PageParam = Annotated[int, Query(ge=1)]
PageSizeParam = Annotated[int, Query(ge=1, le=100)]


def _to_out(lead: object, owner_name: str | None = None) -> LeadOut:
    out = LeadOut.model_validate(lead)
    out.owner_name = owner_name
    return out


@router.post("", status_code=201, summary="创建线索（自动触发 AI 评分，附撞单提示）")
async def create_lead(
    body: LeadCreate, session: SessionDep, current_user: CurrentUserDep
) -> LeadCreateResult:
    lead, warnings = await lead_service.create_lead(session, current_user, body)
    return LeadCreateResult(lead=_to_out(lead), duplicate_warnings=warnings)


@router.get("", summary="线索列表（默认按分数倒序）")
async def list_leads(
    session: SessionDep,
    current_user: CurrentUserDep,
    status: LeadStatus | None = None,
    score_gte: Annotated[int | None, Query(ge=0, le=100)] = None,
    owner_id: uuid.UUID | None = None,
    sort: str | None = "-score",
    page: PageParam = 1,
    page_size: PageSizeParam = 20,
) -> PageResult[LeadOut]:
    rows, total = await lead_service.list_leads(
        session,
        current_user,
        status=status,
        score_gte=score_gte,
        owner_id=owner_id,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    return PageResult(
        items=[_to_out(lead, owner_name) for lead, owner_name in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/import-template", summary="下载 Excel 导入模板")
async def download_import_template(current_user: CurrentUserDep) -> Response:
    content = lead_service.build_import_template()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="leads_import_template.xlsx"'},
    )


@router.post("/import", summary="Excel 批量导入（行号级错误报告 + 撞单提示）")
async def import_leads(
    file: UploadFile, session: SessionDep, current_user: CurrentUserDep
) -> LeadImportReport:
    return await lead_service.import_leads(session, current_user, file.file)


@router.post("/assign", summary="批量分配（manager/admin）")
async def assign_leads(
    body: AssignRequest, session: SessionDep, current_user: CurrentUserDep
) -> AssignResult:
    return await lead_service.assign_leads(session, current_user, body.lead_ids, body.owner_id)


@router.get("/{lead_id}", summary="线索详情（含评分理由与跟进记录）")
async def get_lead(
    lead_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> LeadDetail:
    lead, owner_name, activities = await lead_service.get_lead_detail(
        session, current_user, lead_id
    )
    detail = LeadDetail.model_validate(lead)
    detail.owner_name = owner_name
    detail.activities = [ActivityOut.model_validate(a) for a in activities]
    return detail


@router.patch("/{lead_id}", summary="更新线索/改状态")
async def update_lead(
    lead_id: uuid.UUID, body: LeadUpdate, session: SessionDep, current_user: CurrentUserDep
) -> LeadOut:
    lead = await lead_service.update_lead(session, current_user, lead_id, body)
    return _to_out(lead)


@router.post("/{lead_id}/score", status_code=202, summary="触发/重算 AI 评分（异步）")
async def rescore_lead(
    lead_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> dict[str, str]:
    await lead_service.trigger_rescore(session, current_user, lead_id)
    return {"message": "评分任务已提交，请稍后刷新查看"}


@router.post("/{lead_id}/convert", summary="转化为客户+联系人+商机（事务）")
async def convert_lead(
    lead_id: uuid.UUID,
    body: ConvertRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> ConvertResult:
    return await lead_service.convert_lead(session, current_user, lead_id, body)
