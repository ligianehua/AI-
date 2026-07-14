"""迁移可升可降测试：upgrade head → downgrade base → upgrade head。"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from tests.pg_provision import run_alembic

EXPECTED_TABLES = {
    "teams",
    "users",
    "accounts",
    "contacts",
    "leads",
    "opportunities",
    "activities",
    "scripts",
    "knowledge_docs",
    "knowledge_chunks",
    "llm_calls",
    "notifications",
}


async def _table_names(url: str) -> set[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            return {row[0] for row in rows}
    finally:
        await engine.dispose()


@pytest.fixture
async def migration_db_url(database_url: str) -> AsyncIterator[str]:
    """在同一 PG 实例上建一个独立库，避免影响会话级测试 schema。"""
    admin_engine = create_async_engine(database_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.execute(text("DROP DATABASE IF EXISTS migration_test"))
        await conn.execute(text("CREATE DATABASE migration_test"))
    await admin_engine.dispose()

    # str(URL) 会把密码打码成 ***，子进程 alembic 会拿字面 *** 去认证——必须显式保留密码
    yield make_url(database_url).set(database="migration_test").render_as_string(
        hide_password=False
    )


async def test_upgrade_downgrade_cycle(migration_db_url: str) -> None:
    run_alembic(migration_db_url, "upgrade", "head")
    tables = await _table_names(migration_db_url)
    assert tables >= EXPECTED_TABLES

    run_alembic(migration_db_url, "downgrade", "base")
    tables = await _table_names(migration_db_url)
    assert not (EXPECTED_TABLES & tables), "downgrade 后业务表应全部删除"

    run_alembic(migration_db_url, "upgrade", "head")
    tables = await _table_names(migration_db_url)
    assert tables >= EXPECTED_TABLES
