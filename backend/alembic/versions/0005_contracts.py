"""M10 合同处理：contracts 表

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contracts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="processing", nullable=False),
        sa.Column("extracted", JSONB(), nullable=True),
        sa.Column("review", JSONB(), nullable=True),
        sa.Column("error_msg", sa.String(length=500), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.id"],
            name=op.f("fk_contracts_opportunity_id_opportunities"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_contracts_owner_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contracts")),
    )
    op.create_index(op.f("ix_contracts_owner_id"), "contracts", ["owner_id"])
    op.create_index(op.f("ix_contracts_status"), "contracts", ["status"])


def downgrade() -> None:
    op.drop_table("contracts")
