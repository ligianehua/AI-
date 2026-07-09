from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppModel


class Team(AppModel):
    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String(50), unique=True)
