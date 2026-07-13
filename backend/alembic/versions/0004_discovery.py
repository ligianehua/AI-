"""M8 线索发现：discovery_subscriptions + discovery_candidates

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discovery_subscriptions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("country", sa.String(length=50), nullable=False),
        sa.Column("city", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("keyword", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_new", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_discovery_subscriptions_owner_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discovery_subscriptions")),
    )
    op.create_index(
        op.f("ix_discovery_subscriptions_owner_id"),
        "discovery_subscriptions",
        ["owner_id"],
    )

    op.create_table(
        "discovery_candidates",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("place_id", sa.String(length=300), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("country", sa.String(length=50), nullable=False),
        sa.Column("city", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("duplicate_hint", sa.String(length=300), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("claimed_lead_id", sa.Uuid(), nullable=True),
        sa.Column("raw", JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["discovery_subscriptions.id"],
            name=op.f("fk_discovery_candidates_subscription_id_discovery_subscriptions"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_discovery_candidates_owner_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["claimed_lead_id"],
            ["leads.id"],
            name=op.f("fk_discovery_candidates_claimed_lead_id_leads"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discovery_candidates")),
    )
    op.create_index(
        op.f("ix_discovery_candidates_subscription_id"),
        "discovery_candidates",
        ["subscription_id"],
    )
    op.create_index(
        op.f("ix_discovery_candidates_owner_id"), "discovery_candidates", ["owner_id"]
    )
    op.create_index(op.f("ix_discovery_candidates_status"), "discovery_candidates", ["status"])
    # 同一商户全库只入池一次（软删行不占名额），与线索撞单防护同一哲学
    op.create_index(
        "uq_discovery_candidates_place_id_active",
        "discovery_candidates",
        ["place_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("discovery_candidates")
    op.drop_table("discovery_subscriptions")
