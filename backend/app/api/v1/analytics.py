from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.ai.client import LLMClient, get_llm_client
from app.ai.schemas import PerformanceInsightOutput
from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.core.exceptions import DomainError
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])

LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]
MonthParam = Annotated[str | None, Query(description="YYYY-MM，默认当月")]


def _parse_month(month: str | None) -> date | None:
    if month is None:
        return None
    try:
        return datetime.strptime(month, "%Y-%m").date()
    except ValueError as exc:
        raise DomainError("month 格式应为 YYYY-MM") from exc


@router.get("/performance", summary="业绩指标：本月 vs 上月（RBAC）")
async def get_performance(
    session: SessionDep, current_user: CurrentUserDep, month: MonthParam = None
) -> dict[str, Any]:
    return await analytics_service.performance_overview(session, current_user, _parse_month(month))


@router.post("/insight", summary="AI 月度归因解读（引用真实指标）")
async def generate_insight(
    session: SessionDep,
    current_user: CurrentUserDep,
    llm: LLMClientDep,
    month: MonthParam = None,
) -> PerformanceInsightOutput:
    return await analytics_service.generate_insight(
        session, current_user, _parse_month(month), llm=llm
    )
