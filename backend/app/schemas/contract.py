"""M10 合同处理：出入参。"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ContractStatus


class ContractOut(BaseModel):
    id: uuid.UUID
    name: str
    status: ContractStatus
    opportunity_id: uuid.UUID | None
    extracted: dict[str, Any] | None
    review: dict[str, Any] | None
    error_msg: str | None
    owner_name: str
    created_at: datetime


class GenerateDraftRequest(BaseModel):
    opportunity_id: uuid.UUID
    payment_terms: str | None = Field(None, max_length=500, description="自定义付款方式（可选）")
