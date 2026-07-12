import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ActivityRelatedType, ActivityType


class ActivityCreate(BaseModel):
    related_type: ActivityRelatedType
    related_id: uuid.UUID
    type: ActivityType
    content: str = Field(min_length=1, max_length=5000)
    next_action: str | None = Field(default=None, max_length=1000)
    next_action_date: date | None = None


class ActivityUpdate(BaseModel):
    type: ActivityType | None = None
    content: str | None = Field(default=None, min_length=1, max_length=5000)
    next_action: str | None = Field(default=None, max_length=1000)
    next_action_date: date | None = None


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    related_type: ActivityRelatedType
    related_id: uuid.UUID
    type: ActivityType
    content: str
    next_action: str | None
    next_action_date: date | None
    owner_id: uuid.UUID
    owner_name: str | None = None
    created_at: datetime
