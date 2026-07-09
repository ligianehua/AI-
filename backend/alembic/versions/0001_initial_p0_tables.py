"""P0 全部数据表（PLAN.md §4）

Revision ID: 0001
Revises:
Create Date: 2026-07-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "teams",
        *_common_columns(),
        sa.Column("name", sa.String(50), nullable=False),
        sa.UniqueConstraint("name", name="uq_teams_name"),
    )

    op.create_table(
        "users",
        *_common_columns(),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("teams.id", name="fk_users_team_id_teams"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "accounts",
        *_common_columns(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("industry", sa.String(50), nullable=True),
        sa.Column("size", sa.String(20), nullable=True),
        sa.Column("region", sa.String(50), nullable=True),
        sa.Column("website", sa.String(200), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", name="fk_accounts_owner_id_users"),
            nullable=False,
        ),
        sa.Column("ai_profile", JSONB(), nullable=True),
        sa.Column("ai_profile_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_accounts_name", "accounts", ["name"])
    op.create_index("ix_accounts_owner_id", "accounts", ["owner_id"])

    op.create_table(
        "opportunities",
        *_common_columns(),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("accounts.id", name="fk_opportunities_account_id_accounts"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("stage", sa.String(20), server_default="initial", nullable=False),
        sa.Column("probability", sa.Integer(), server_default=sa.text("10"), nullable=False),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", name="fk_opportunities_owner_id_users"),
            nullable=False,
        ),
        sa.Column("lost_reason", sa.Text(), nullable=True),
        sa.Column("stage_history", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.create_index("ix_opportunities_account_id", "opportunities", ["account_id"])
    op.create_index("ix_opportunities_stage", "opportunities", ["stage"])
    op.create_index("ix_opportunities_owner_id", "opportunities", ["owner_id"])

    op.create_table(
        "contacts",
        *_common_columns(),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey(
                "accounts.id", name="fk_contacts_account_id_accounts", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("title", sa.String(50), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("wechat", sa.String(64), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("role_in_deal", sa.String(20), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
    )
    op.create_index("ix_contacts_account_id", "contacts", ["account_id"])

    op.create_table(
        "leads",
        *_common_columns(),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("account_name", sa.String(200), nullable=False),
        sa.Column("contact_name", sa.String(50), nullable=True),
        sa.Column("contact_phone", sa.String(30), nullable=True),
        sa.Column("contact_wechat", sa.String(64), nullable=True),
        sa.Column("industry", sa.String(50), nullable=True),
        sa.Column("requirement_desc", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), server_default="new", nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("score_detail", JSONB(), nullable=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", name="fk_leads_owner_id_users"),
            nullable=False,
        ),
        sa.Column(
            "converted_account_id",
            sa.Uuid(),
            sa.ForeignKey("accounts.id", name="fk_leads_converted_account_id_accounts"),
            nullable=True,
        ),
        sa.Column(
            "converted_opportunity_id",
            sa.Uuid(),
            sa.ForeignKey(
                "opportunities.id", name="fk_leads_converted_opportunity_id_opportunities"
            ),
            nullable=True,
        ),
    )
    op.create_index("ix_leads_contact_phone", "leads", ["contact_phone"])
    op.create_index("ix_leads_status", "leads", ["status"])
    op.create_index("ix_leads_owner_id", "leads", ["owner_id"])

    op.create_table(
        "activities",
        *_common_columns(),
        sa.Column("related_type", sa.String(20), nullable=False),
        sa.Column("related_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("next_action_date", sa.Date(), nullable=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", name="fk_activities_owner_id_users"),
            nullable=False,
        ),
    )
    op.create_index("ix_activities_related", "activities", ["related_type", "related_id"])
    op.create_index("ix_activities_owner_id", "activities", ["owner_id"])

    op.create_table(
        "scripts",
        *_common_columns(),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("scenario", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "tags", ARRAY(sa.String()), server_default=sa.text("'{}'::text[]"), nullable=False
        ),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("usage_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", name="fk_scripts_created_by_users"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index("ix_scripts_category", "scripts", ["category"])

    op.create_table(
        "knowledge_docs",
        *_common_columns(),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), server_default="processing", nullable=False),
    )

    op.create_table(
        "knowledge_chunks",
        *_common_columns(),
        sa.Column(
            "doc_id",
            sa.Uuid(),
            sa.ForeignKey(
                "knowledge_docs.id",
                name="fk_knowledge_chunks_doc_id_knowledge_docs",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
    )
    op.create_index("ix_knowledge_chunks_doc_id", "knowledge_chunks", ["doc_id"])

    op.create_table(
        "llm_calls",
        *_common_columns(),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", name="fk_llm_calls_user_id_users"),
            nullable=True,
        ),
        sa.Column("task_type", sa.String(30), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("tokens_in", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("tokens_out", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cost_estimate", sa.Numeric(10, 4), server_default=sa.text("0"), nullable=False),
        sa.Column("latency_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("feedback", sa.SmallInteger(), nullable=True),
    )
    op.create_index("ix_llm_calls_user_id", "llm_calls", ["user_id"])
    op.create_index("ix_llm_calls_task_type", "llm_calls", ["task_type"])

    op.create_table(
        "notifications",
        *_common_columns(),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", name="fk_notifications_user_id_users"),
            nullable=False,
        ),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("related_type", sa.String(20), nullable=True),
        sa.Column("related_id", sa.Uuid(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("llm_calls")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_docs")
    op.drop_table("scripts")
    op.drop_table("activities")
    op.drop_table("leads")
    op.drop_table("contacts")
    op.drop_table("opportunities")
    op.drop_table("accounts")
    op.drop_table("users")
    op.drop_table("teams")
    op.execute("DROP EXTENSION IF EXISTS vector")
