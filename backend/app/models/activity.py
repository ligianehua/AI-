import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppModel


class Activity(AppModel):
    """跟进记录，多态挂载到 lead / account / opportunity。"""

    __tablename__ = "activities"
    __table_args__ = (Index("ix_activities_related", "related_type", "related_id"),)

    related_type: Mapped[str] = mapped_column(String(20))  # lead | account | opportunity
    related_id: Mapped[uuid.UUID] = mapped_column()
    type: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)
    next_action_date: Mapped[date | None] = mapped_column(Date)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
