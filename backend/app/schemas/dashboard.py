import uuid
from datetime import date

from pydantic import BaseModel

from app.models.enums import ActivityRelatedType, OpportunityStage


class TodoItem(BaseModel):
    """今日待办：next_action 已到期（含逾期）的跟进计划。"""

    activity_id: uuid.UUID
    next_action: str
    next_action_date: date
    related_type: ActivityRelatedType
    related_label: str
    overdue: bool


class FunnelItem(BaseModel):
    stage: OpportunityStage
    count: int


class DashboardSummary(BaseModel):
    """工作台摘要（统计按当前用户可见域；待办只看本人）。金额单位 CNY。"""

    lead_count: int
    account_count: int
    opportunity_count: int
    pipeline_amount: float  # 在途商机金额（未赢单/输单）
    won_amount_this_month: float  # 本月成交额（won 按进入赢单阶段时间归月）
    funnel: list[FunnelItem]
    todos: list[TodoItem]
