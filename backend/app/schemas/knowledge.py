import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import KnowledgeDocStatus


class KnowledgeDocOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: KnowledgeDocStatus
    chunk_count: int = 0
    created_at: datetime
