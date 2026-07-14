import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppModel
from app.models.enums import ContractStatus


class Contract(AppModel):
    """合同：上传原文（data/uploads/contracts）→ AI 抽取要素 + 风险审查。

    extracted / review 结构见 ai/schemas.py（ContractExtractOutput / ContractReviewOutput）。
    AI 输出仅为提示，不构成法律意见（UI 与生成文档均有声明）。
    """

    __tablename__ = "contracts"

    name: Mapped[str] = mapped_column(String(200))
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunities.id"))
    status: Mapped[str] = mapped_column(
        String(20),
        default=ContractStatus.PROCESSING,
        server_default=ContractStatus.PROCESSING.value,
        index=True,
    )
    extracted: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    review: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_msg: Mapped[str | None] = mapped_column(String(500))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
