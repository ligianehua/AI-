"""pg_trgm 扩展 + 话术/知识块内容检索索引（混合检索的关键词路）

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-12

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # trgm 索引纯属性能优化（加速关键词路的 ILIKE '%词%'）。部分精简发行版
    # （如本地开发用的 pgserver 二进制）不带 pg_trgm，此时跳过——检索结果不受影响，
    # 只是无索引顺序扫描；docker 的 pgvector/pgvector:pg16 镜像包含 pg_trgm。
    op.execute(
        """
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS pg_trgm;
            CREATE INDEX IF NOT EXISTS ix_scripts_content_trgm
                ON scripts USING gin (content gin_trgm_ops);
            CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_content_trgm
                ON knowledge_chunks USING gin (content gin_trgm_ops);
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'pg_trgm unavailable, skip trgm indexes: %', SQLERRM;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_content_trgm")
    op.execute("DROP INDEX IF EXISTS ix_scripts_content_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
