"""M11 销售预测：forecast_snapshots 表

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "forecast_snapshots",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("weighted_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("open_count", sa.Integer(), nullable=False),
        sa.Column("by_stage", JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_forecast_snapshots_owner_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forecast_snapshots")),
    )
    op.create_index(
        op.f("ix_forecast_snapshots_snapshot_date"), "forecast_snapshots", ["snapshot_date"]
    )
    op.create_index(op.f("ix_forecast_snapshots_owner_id"), "forecast_snapshots", ["owner_id"])
    op.create_index(
        "uq_forecast_snapshots_owner_date_active",
        "forecast_snapshots",
        ["owner_id", "snapshot_date"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("forecast_snapshots")
