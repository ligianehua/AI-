from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import RoleUsers

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


async def test_login_success(client: AsyncClient, roles: RoleUsers) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "sales_a@test.cn", "password": "password123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_wrong_password(client: AsyncClient, roles: RoleUsers) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "sales_a@test.cn", "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_credentials"


async def test_login_unknown_email(client: AsyncClient, roles: RoleUsers) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.cn", "password": "password123"},
    )
    assert resp.status_code == 401


async def test_login_inactive_user(
    client: AsyncClient, roles: RoleUsers, session: AsyncSession
) -> None:
    roles.sales_b.is_active = False
    await session.commit()
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "sales_b@test.cn", "password": "password123"},
    )
    assert resp.status_code == 401
    assert "停用" in resp.json()["message"]


async def test_me(client: AsyncClient, roles: RoleUsers, login: LoginFn) -> None:
    headers = await login("manager_a@test.cn")
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "manager_a@test.cn"
    assert body["role"] == "manager"
    assert body["team_id"] == str(roles.team_a.id)


async def test_me_without_token(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "not_authenticated"


async def test_me_with_bad_token(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401
