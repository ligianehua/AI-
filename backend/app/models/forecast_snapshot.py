import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppModel


class ForecastSnapshot(AppModel):
    """加权 pipeline 周度快照（按 owner 粒度存，读取时按可见域聚合）。

    (owner_id, snapshot_date) 部分唯一：同日重跑覆盖，幂等。
    """

    __tablename__ = "forecast_snapshots"

    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    weighted_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    open_count: Mapped[int] = mapped_column(Integer)
    by_stage: Mapped[dict[str, Any]] = mapped_column(JSONB)

    __table_args__ = (
        Index(
            "uq_forecast_snapshots_owner_date_active",
            "owner_id",
            "snapshot_date",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
