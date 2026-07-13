import uuid

from sqlalchemy import Boolean, ForeignKey, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppModel


class User(AppModel):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(50))
    # 唯一性由部分唯一索引保证（迁移 0003，WHERE deleted_at IS NULL）：软删后邮箱可复用
    email: Mapped[str] = mapped_column(String(255), index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10))  # sales | manager | admin
    team_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teams.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
