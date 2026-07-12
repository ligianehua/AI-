import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.ai.client import LLMClient, get_llm_client
from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.schemas.opportunity import (
    KanbanResponse,
    NextActionsResponse,
    OpportunityCreate,
    OpportunityOut,
    OpportunityUpdate,
    StageChangeRequest,
)
from app.services import next_action, opportunity_service

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.post("", status_code=201, summary="创建商机")
async def create_opportunity(
    body: OpportunityCreate, session: SessionDep, current_user: CurrentUserDep
) -> OpportunityOut:
    opp = await opportunity_service.create_opportunity(session, current_user, body)
    return await opportunity_service.get_opportunity_out(session, current_user, opp.id)


@router.get("/kanban", summary="阶段看板（含金额/加权金额汇总）")
async def get_kanban(session: SessionDep, current_user: CurrentUserDep) -> KanbanResponse:
    return await opportunity_service.get_kanban(session, current_user)


@router.get("/{opportunity_id}", summary="商机详情")
async def get_opportunity(
    opportunity_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> OpportunityOut:
    return await opportunity_service.get_opportunity_out(session, current_user, opportunity_id)


@router.patch("/{opportunity_id}", summary="更新商机")
async def update_opportunity(
    opportunity_id: uuid.UUID,
    body: OpportunityUpdate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> OpportunityOut:
    await opportunity_service.update_opportunity(session, current_user, opportunity_id, body)
    return await opportunity_service.get_opportunity_out(session, current_user, opportunity_id)


@router.patch("/{opportunity_id}/stage", summary="换阶段（won 需金额确认 / lost 需原因）")
async def change_stage(
    opportunity_id: uuid.UUID,
    body: StageChangeRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> OpportunityOut:
    await opportunity_service.change_stage(session, current_user, opportunity_id, body)
    return await opportunity_service.get_opportunity_out(session, current_user, opportunity_id)


LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]


@router.get("/{opportunity_id}/next-actions", summary="AI 下一步建议（3 条）")
async def get_next_actions(
    opportunity_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
    llm: LLMClientDep,
) -> NextActionsResponse:
    output = await next_action.get_next_actions(session, current_user, opportunity_id, llm=llm)
    return NextActionsResponse(actions=[a.model_dump() for a in output.actions])
