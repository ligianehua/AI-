from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppModel
from app.models.enums import KnowledgeDocStatus


class KnowledgeDoc(AppModel):
    __tablename__ = "knowledge_docs"

    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(20),
        default=KnowledgeDocStatus.PROCESSING,
        server_default=KnowledgeDocStatus.PROCESSING.value,
    )
