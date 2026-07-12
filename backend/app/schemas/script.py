import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ScriptCategory


class ScriptCreate(BaseModel):
    category: ScriptCategory
    scenario: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=10)


class ScriptUpdate(BaseModel):
    category: ScriptCategory | None = None
    scenario: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=5000)
    tags: list[str] | None = Field(default=None, max_length=10)
    is_active: bool | None = None


class ScriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: ScriptCategory
    scenario: str
    content: str
    tags: list[str]
    usage_count: int
    is_active: bool
    has_embedding: bool = False
    created_at: datetime


class ScriptSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    category: ScriptCategory | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class ScriptSearchHit(BaseModel):
    script: ScriptOut
    score: float


class RecommendRequest(BaseModel):
    scenario: ScriptCategory
    channel: str = Field(pattern="^(wechat|email|phone)$")
    opportunity_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    user_hint: str | None = Field(default=None, max_length=500)


class FeedbackRequest(BaseModel):
    llm_call_id: uuid.UUID
    feedback: int = Field(ge=-1, le=1)  # 1 赞 / -1 踩
