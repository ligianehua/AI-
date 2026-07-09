import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppModel
from app.models.enums import LeadStatus


class Lead(AppModel):
    __tablename__ = "leads"

    source: Mapped[str] = mapped_column(String(20))
    account_name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str | None] = mapped_column(String(50))
    contact_phone: Mapped[str | None] = mapped_column(String(30), index=True)
    contact_wechat: Mapped[str | None] = mapped_column(String(64))
    industry: Mapped[str | None] = mapped_column(String(50))
    requirement_desc: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), default=LeadStatus.NEW, server_default=LeadStatus.NEW.value, index=True
    )
    score: Mapped[int | None] = mapped_column(Integer)
    score_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    converted_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"))
    converted_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunities.id")
    )
