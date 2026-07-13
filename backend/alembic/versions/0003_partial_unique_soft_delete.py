"""users.email / teams.name 唯一性改为部分唯一索引（软删行不占用名额）

软删用户/团队后需要能重建同 email/同名（此前全表唯一索引会 IntegrityError 500）。

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.create_index(
        "ix_users_email",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_constraint("uq_teams_name", "teams", type_="unique")
    op.create_index(
        "uq_teams_name_active",
        "teams",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    # 注意：若存在"软删后重建同名"的数据，降级会因全表唯一冲突失败，需先人工清理
    op.drop_index("uq_teams_name_active", table_name="teams")
    op.create_unique_constraint("uq_teams_name", "teams", ["name"])
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)
