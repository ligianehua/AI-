import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ActivityRelatedType, ActivityType
from app.schemas.contact import ContactOut


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=50)
    size: str | None = Field(default=None, max_length=20)
    region: str | None = Field(default=None, max_length=50)
    website: str | None = Field(default=None, max_length=200)
    remark: str | None = Field(default=None, max_length=5000)


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=50)
    size: str | None = Field(default=None, max_length=20)
    region: str | None = Field(default=None, max_length=50)
    website: str | None = Field(default=None, max_length=200)
    remark: str | None = Field(default=None, max_length=5000)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    industry: str | None
    size: str | None
    region: str | None
    website: str | None
    remark: str | None
    owner_id: uuid.UUID
    owner_name: str | None = None
    ai_profile: dict[str, Any] | None
    ai_profile_updated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AccountDetail(AccountOut):
    contacts: list[ContactOut] = []


class TimelineItem(BaseModel):
    """跨 lead/account/opportunity 聚合的跟进记录。"""

    id: uuid.UUID
    related_type: ActivityRelatedType
    related_label: str  # 如「线索：xx分公司」「商机：xx采购」「客户跟进」
    type: ActivityType
    content: str
    next_action: str | None
    next_action_date: date | None
    owner_name: str
    created_at: datetime
