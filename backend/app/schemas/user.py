import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import Role
from app.schemas.common import forbid_explicit_null


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role
    team_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    _no_null = forbid_explicit_null("name", "role", "is_active")

    name: str | None = Field(default=None, min_length=1, max_length=50)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: Role | None = None
    team_id: uuid.UUID | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: EmailStr
    role: Role
    team_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
