import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, SmallInteger, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppModel


class LlmCall(AppModel):
    """AI 调用审计：成本 + 可观测 + 用户反馈落点。"""

    __tablename__ = "llm_calls"

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(30), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(64))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    cost_estimate: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0"), server_default=text("0")
    )  # 单位 CNY
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(10))  # ok | error | timeout
    error_msg: Mapped[str | None] = mapped_column(Text)
    feedback: Mapped[int | None] = mapped_column(SmallInteger)  # 1 赞 / -1 踩
