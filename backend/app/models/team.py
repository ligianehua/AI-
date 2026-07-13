from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppModel


class Team(AppModel):
    __tablename__ = "teams"

    # 唯一性由部分唯一索引保证（迁移 0003，WHERE deleted_at IS NULL）：软删后名称可复用
    name: Mapped[str] = mapped_column(String(50))
