import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, text, true
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppModel


class Script(AppModel):
    __tablename__ = "scripts"

    category: Mapped[str] = mapped_column(String(20), index=True)
    scenario: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default=text("'{}'::text[]")
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    usage_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
