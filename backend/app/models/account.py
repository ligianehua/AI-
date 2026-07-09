import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppModel


class Account(AppModel):
    __tablename__ = "accounts"

    name: Mapped[str] = mapped_column(String(200), index=True)
    industry: Mapped[str | None] = mapped_column(String(50))
    size: Mapped[str | None] = mapped_column(String(20))
    region: Mapped[str | None] = mapped_column(String(50))
    website: Mapped[str | None] = mapped_column(String(200))
    remark: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    ai_profile: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ai_profile_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
