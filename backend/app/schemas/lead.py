import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import LeadSource, LeadStatus
from app.schemas.activity import ActivityOut

PHONE_PATTERN = r"^1\d{10}$"


class LeadCreate(BaseModel):
    source: LeadSource
    account_name: str = Field(min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=50)
    contact_phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    contact_wechat: str | None = Field(default=None, max_length=64)
    industry: str | None = Field(default=None, max_length=50)
    requirement_desc: str | None = Field(default=None, max_length=5000)


class LeadUpdate(BaseModel):
    source: LeadSource | None = None
    account_name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=50)
    contact_phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    contact_wechat: str | None = Field(default=None, max_length=64)
    industry: str | None = Field(default=None, max_length=50)
    requirement_desc: str | None = Field(default=None, max_length=5000)
    status: LeadStatus | None = None  # converted 只能通过转化接口设置


class DuplicateWarning(BaseModel):
    lead_id: uuid.UUID
    account_name: str
    owner_name: str
    matched_field: str  # contact_phone | account_name


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: LeadSource
    account_name: str
    contact_name: str | None
    contact_phone: str | None
    contact_wechat: str | None
    industry: str | None
    requirement_desc: str | None
    status: LeadStatus
    score: int | None
    score_detail: dict[str, Any] | None
    owner_id: uuid.UUID
    owner_name: str | None = None
    converted_account_id: uuid.UUID | None
    converted_opportunity_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class LeadCreateResult(BaseModel):
    lead: LeadOut
    duplicate_warnings: list[DuplicateWarning]


class LeadDetail(LeadOut):
    activities: list[ActivityOut] = []


class ImportRowError(BaseModel):
    row: int  # Excel 行号（含表头，从 2 开始）
    reason: str


class LeadImportReport(BaseModel):
    total_rows: int
    imported: int
    failed: int
    errors: list[ImportRowError]
    duplicate_warnings: list[ImportRowError]  # 疑似撞单提示（不拦截导入）


class ConvertRequest(BaseModel):
    account_name: str | None = Field(default=None, min_length=1, max_length=200)
    opportunity_name: str | None = Field(default=None, min_length=1, max_length=200)
    amount: Decimal | None = Field(default=None, ge=0, le=Decimal("999999999999"))


class ConvertResult(BaseModel):
    account_id: uuid.UUID
    contact_id: uuid.UUID | None
    opportunity_id: uuid.UUID


class AssignRequest(BaseModel):
    lead_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    owner_id: uuid.UUID


class AssignResult(BaseModel):
    assigned: int
