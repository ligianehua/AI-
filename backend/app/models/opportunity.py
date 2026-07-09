import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppModel
from app.models.enums import OpportunityStage


class Opportunity(AppModel):
    __tablename__ = "opportunities"

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), server_default=text("0")
    )  # 单位 CNY
    stage: Mapped[str] = mapped_column(
        String(20),
        default=OpportunityStage.INITIAL,
        server_default=OpportunityStage.INITIAL.value,
        index=True,
    )
    probability: Mapped[int] = mapped_column(Integer, default=10, server_default=text("10"))
    expected_close_date: Mapped[date | None] = mapped_column(Date)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    lost_reason: Mapped[str | None] = mapped_column(Text)
    stage_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )  # [{stage, entered_at, by}]
