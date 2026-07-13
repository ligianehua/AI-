import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppModel
from app.models.enums import CandidateStatus


class DiscoveryCandidate(AppModel):
    """线索发现候选池：抓取结果先进池，销售领取后才成为正式线索。

    place_id 全库唯一（部分索引，见迁移 0004）：同一商户只入池一次，
    先到先得——这与线索撞单防护是同一哲学。
    """

    __tablename__ = "discovery_candidates"

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_subscriptions.id"), index=True
    )
    place_id: Mapped[str] = mapped_column(String(300))
    name: Mapped[str] = mapped_column(String(300))
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(50))
    website: Mapped[str | None] = mapped_column(String(500))
    country: Mapped[str] = mapped_column(String(50))
    city: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(20),
        default=CandidateStatus.PENDING,
        server_default=CandidateStatus.PENDING.value,
        index=True,
    )
    duplicate_hint: Mapped[str | None] = mapped_column(String(300))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    claimed_lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        Index(
            "uq_discovery_candidates_place_id_active",
            "place_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
