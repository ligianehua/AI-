import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import OpportunityStage


class OpportunityCreate(BaseModel):
    account_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(default=Decimal(0), ge=0, le=Decimal("999999999999"))
    expected_close_date: date | None = None


class OpportunityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    amount: Decimal | None = Field(default=None, ge=0, le=Decimal("999999999999"))
    probability: int | None = Field(default=None, ge=0, le=100)
    expected_close_date: date | None = None


class StageChangeRequest(BaseModel):
    stage: OpportunityStage
    lost_reason: str | None = Field(default=None, max_length=2000)  # lost 必填
    amount: Decimal | None = Field(default=None, ge=0, le=Decimal("999999999999"))  # won 必填确认


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    account_name: str | None = None
    name: str
    amount: Decimal
    stage: OpportunityStage
    probability: int
    expected_close_date: date | None
    owner_id: uuid.UUID
    owner_name: str | None = None
    lost_reason: str | None
    stage_history: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    stuck_days: int = 0  # 当前阶段停留天数
    last_activity_at: datetime | None = None


class KanbanColumn(BaseModel):
    stage: OpportunityStage
    total_amount: float
    weighted_amount: float  # Σ 金额 × 概率
    items: list[OpportunityOut]


class KanbanResponse(BaseModel):
    columns: list[KanbanColumn]


class NextActionsResponse(BaseModel):
    actions: list[dict[str, Any]]  # NextActionItem 结构：action/reason/suggested_script_scenario
