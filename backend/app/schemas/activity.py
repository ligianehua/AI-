import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ActivityType


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: ActivityType
    content: str
    next_action: str | None
    next_action_date: date | None
    owner_id: uuid.UUID
    created_at: datetime
