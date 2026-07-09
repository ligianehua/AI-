from fastapi import APIRouter

from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.schemas.dashboard import DashboardSummary
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", summary="工作台摘要（按可见域统计）")
async def get_summary(session: SessionDep, current_user: CurrentUserDep) -> DashboardSummary:
    return await dashboard_service.summary(session, current_user)
