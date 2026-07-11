import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ContactRoleInDeal


class ContactCreate(BaseModel):
    account_id: uuid.UUID
    name: str = Field(min_length=1, max_length=50)
    title: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=30)
    wechat: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    role_in_deal: ContactRoleInDeal | None = None
    remark: str | None = Field(default=None, max_length=2000)


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    title: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=30)
    wechat: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    role_in_deal: ContactRoleInDeal | None = None
    remark: str | None = Field(default=None, max_length=2000)


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    title: str | None
    phone: str | None
    wechat: str | None
    email: str | None
    role_in_deal: ContactRoleInDeal | None
    remark: str | None
    created_at: datetime
