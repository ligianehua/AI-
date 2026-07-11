import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient
from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.ai.client import LLMClient
from app.core.db import get_session
from app.core.security import hash_password
from app.main import app
from app.models import Team, User
from app.models.enums import Role
from tests.fake_llm import FakeOpenAI

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_PASSWORD = "password123"

_TABLES = (
    "notifications, llm_calls, knowledge_chunks, knowledge_docs, scripts, "
    "activities, leads, contacts, opportunities, accounts, users, teams"
)


def run_alembic(url: str, *args: str) -> None:
    env = {**os.environ, "ALEMBIC_DATABASE_URL": url}
    subprocess.run([sys.executable, "-m", "alembic", *args], check=True, cwd=BACKEND_DIR, env=env)


def _provision_pg() -> tuple[str, Callable[[], None]]:
    """测试库三级供给：TEST_DATABASE_URL > Docker testcontainers > 本地 PG 二进制。"""
    if url := os.environ.get("TEST_DATABASE_URL"):
        return url, lambda: None

    if shutil.which("docker"):
        try:
            from testcontainers.postgres import PostgresContainer

            container = PostgresContainer("pgvector/pgvector:pg16", driver="asyncpg")
            container.start()
            return container.get_connection_url(), lambda: container.stop()
        except Exception as exc:  # noqa: BLE001 - docker 不可用则回退本地
            print(f"testcontainers 不可用（{exc}），回退本地 PostgreSQL")

    from scripts import local_pg

    local_pg.ensure_binaries()
    datadir = Path(tempfile.mkdtemp(prefix="ai_sales_test_pg_"))
    local_pg.init_cluster(datadir)
    port = local_pg.free_port()
    local_pg.start(datadir, port)
    local_pg.ensure_database(port, "app_test")

    def cleanup() -> None:
        local_pg.stop(datadir)
        shutil.rmtree(datadir, ignore_errors=True)

    return local_pg.async_url(port, "app_test"), cleanup


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    url, cleanup = _provision_pg()
    try:
        run_alembic(url, "upgrade", "head")
        yield url
    finally:
        cleanup()


@pytest.fixture(scope="session")
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


@pytest.fixture(autouse=True)
async def _clean_db(engine: AsyncEngine) -> AsyncIterator[None]:
    yield
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {_TABLES} CASCADE"))


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@dataclass
class RoleUsers:
    """三角色测试用户：admin 全量、manager_a 管华东团队、sales_a/sales_a2 华东、sales_b 华北。"""

    team_a: Team
    team_b: Team
    admin: User
    manager_a: User
    sales_a: User
    sales_a2: User
    sales_b: User


@pytest.fixture
async def roles(session: AsyncSession) -> RoleUsers:
    team_a = Team(name="华东测试团队")
    team_b = Team(name="华北测试团队")
    session.add_all([team_a, team_b])
    await session.flush()

    hashed = hash_password(TEST_PASSWORD)

    def make(name: str, email: str, role: Role, team: Team | None) -> User:
        return User(
            name=name,
            email=email,
            hashed_password=hashed,
            role=role,
            team_id=team.id if team else None,
        )

    users = RoleUsers(
        team_a=team_a,
        team_b=team_b,
        admin=make("测试管理员", "admin@test.cn", Role.ADMIN, None),
        manager_a=make("A组主管", "manager_a@test.cn", Role.MANAGER, team_a),
        sales_a=make("A组销售一", "sales_a@test.cn", Role.SALES, team_a),
        sales_a2=make("A组销售二", "sales_a2@test.cn", Role.SALES, team_a),
        sales_b=make("B组销售", "sales_b@test.cn", Role.SALES, team_b),
    )
    session.add_all([users.admin, users.manager_a, users.sales_a, users.sales_a2, users.sales_b])
    await session.commit()
    return users


@pytest.fixture
def fakes() -> dict[str, "FakeOpenAI"]:
    return {"deepseek": FakeOpenAI(), "qwen": FakeOpenAI()}


@pytest.fixture
def llm(engine: AsyncEngine, fakes: dict[str, "FakeOpenAI"]) -> "LLMClient":
    """绑定测试库记账 + fake 供应商的 LLMClient。"""
    maker = async_sessionmaker(engine, expire_on_commit=False)
    return LLMClient(
        sessionmaker=maker,
        client_factory=lambda name, provider: cast(AsyncOpenAI, fakes[name]),
    )


@pytest.fixture
def login(client: AsyncClient) -> Callable[[str], Awaitable[dict[str, str]]]:
    async def _login(email: str, password: str = TEST_PASSWORD) -> dict[str, str]:
        resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200, resp.text
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    return _login
