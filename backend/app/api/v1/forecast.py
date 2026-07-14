from typing import Any

from fastapi import APIRouter

from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.core.exceptions import PermissionDeniedError
from app.models.enums import Role
from app.services import forecast_service
from app.tasks import dispatcher

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.get("", summary="销售预测：加权 pipeline + 快照走势 + 外推（数据量守卫）")
async def get_forecast(session: SessionDep, current_user: CurrentUserDep) -> dict[str, Any]:
    return await forecast_service.forecast_overview(session, current_user)


@router.post("/snapshot", status_code=202, summary="手动生成今日快照（manager/admin）")
async def take_snapshot(session: SessionDep, current_user: CurrentUserDep) -> dict[str, Any]:
    if current_user.role not in (Role.ADMIN, Role.MANAGER):
        raise PermissionDeniedError("快照生成仅限主管和管理员")
    enqueued = await dispatcher.enqueue("forecast_snapshot_task")
    return {"enqueued": enqueued, "message": "快照任务已提交" if enqueued else "提交失败，请重试"}
