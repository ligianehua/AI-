"""M8 线索发现：订阅 + 候选池出入参。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import CandidateStatus
from app.schemas.common import forbid_explicit_null
from app.schemas.lead import DuplicateWarning


class SubscriptionCreate(BaseModel):
    name: str | None = Field(None, max_length=100, description="留空自动取「城市 品类」")
    country: str = Field(min_length=1, max_length=50)
    city: str = Field(min_length=1, max_length=50)
    category: str = Field(min_length=1, max_length=100, description="品类关键词，如 manufacturing")
    keyword: str | None = Field(None, max_length=100)


class SubscriptionUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    country: str | None = Field(None, min_length=1, max_length=50)
    city: str | None = Field(None, min_length=1, max_length=50)
    category: str | None = Field(None, min_length=1, max_length=100)
    keyword: str | None = Field(None, max_length=100)
    is_active: bool | None = None

    _no_null = forbid_explicit_null("name", "country", "city", "category", "is_active")


class SubscriptionOut(BaseModel):
    id: uuid.UUID
    name: str
    country: str
    city: str
    category: str
    keyword: str | None
    is_active: bool
    owner_name: str
    last_run_at: datetime | None
    last_run_new: int | None
    created_at: datetime


class RunResult(BaseModel):
    enqueued: bool
    message: str


class CandidateOut(BaseModel):
    id: uuid.UUID
    subscription_id: uuid.UUID
    name: str
    address: str | None
    phone: str | None
    website: str | None
    country: str
    city: str
    category: str
    status: CandidateStatus
    duplicate_hint: str | None
    claimed_lead_id: uuid.UUID | None
    created_at: datetime


class ClaimResult(BaseModel):
    lead_id: uuid.UUID
    duplicate_warnings: list[DuplicateWarning]
