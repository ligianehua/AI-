from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from tests.conftest import RoleUsers

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


def _new_user_payload(email: str = "newbie@test.cn") -> dict[str, object]:
    return {
        "name": "新销售",
        "email": email,
        "password": "password123",
        "role": "sales",
    }


async def test_admin_can_list_users(client: AsyncClient, roles: RoleUsers, login: LoginFn) -> None:
    headers = await login("admin@test.cn")
    resp = await client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    emails = {u["email"] for u in body["items"]}
    assert "sales_b@test.cn" in emails


@pytest.mark.parametrize("email", ["manager_a@test.cn", "sales_a@test.cn"])
async def test_non_admin_cannot_list_users(
    client: AsyncClient, roles: RoleUsers, login: LoginFn, email: str
) -> None:
    headers = await login(email)
    resp = await client.get("/api/v1/users", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["code"] == "permission_denied"


async def test_admin_create_user_and_new_user_can_login(
    client: AsyncClient, roles: RoleUsers, login: LoginFn
) -> None:
    headers = await login("admin@test.cn")
    payload = _new_user_payload()
    payload["team_id"] = str(roles.team_a.id)
    resp = await client.post("/api/v1/users", json=payload, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["role"] == "sales"

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "newbie@test.cn", "password": "password123"},
    )
    assert resp.status_code == 200


async def test_create_user_duplicate_email(
    client: AsyncClient, roles: RoleUsers, login: LoginFn
) -> None:
    headers = await login("admin@test.cn")
    resp = await client.post(
        "/api/v1/users", json=_new_user_payload("sales_a@test.cn"), headers=headers
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


@pytest.mark.parametrize("email", ["manager_a@test.cn", "sales_a@test.cn"])
async def test_non_admin_cannot_create_user(
    client: AsyncClient, roles: RoleUsers, login: LoginFn, email: str
) -> None:
    headers = await login(email)
    resp = await client.post("/api/v1/users", json=_new_user_payload(), headers=headers)
    assert resp.status_code == 403


async def test_admin_deactivate_user_blocks_login(
    client: AsyncClient, roles: RoleUsers, login: LoginFn
) -> None:
    headers = await login("admin@test.cn")
    resp = await client.patch(
        f"/api/v1/users/{roles.sales_b.id}", json={"is_active": False}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "sales_b@test.cn", "password": "password123"},
    )
    assert resp.status_code == 401


async def test_assignable_users_scoped(
    client: AsyncClient, roles: RoleUsers, login: LoginFn
) -> None:
    resp = await client.get("/api/v1/users/assignable", headers=await login("manager_a@test.cn"))
    assert resp.status_code == 200
    names = {u["name"] for u in resp.json()}
    assert names == {"A组主管", "A组销售一", "A组销售二"}  # 只有本团队

    resp = await client.get("/api/v1/users/assignable", headers=await login("admin@test.cn"))
    assert len(resp.json()) == 5

    resp = await client.get("/api/v1/users/assignable", headers=await login("sales_a@test.cn"))
    assert resp.status_code == 403


async def test_admin_cannot_delete_self(
    client: AsyncClient, roles: RoleUsers, login: LoginFn
) -> None:
    headers = await login("admin@test.cn")
    resp = await client.delete(f"/api/v1/users/{roles.admin.id}", headers=headers)
    assert resp.status_code == 400


async def test_admin_delete_user(client: AsyncClient, roles: RoleUsers, login: LoginFn) -> None:
    headers = await login("admin@test.cn")
    resp = await client.delete(f"/api/v1/users/{roles.sales_a2.id}", headers=headers)
    assert resp.status_code == 204

    resp = await client.get("/api/v1/users", headers=headers)
    emails = {u["email"] for u in resp.json()["items"]}
    assert "sales_a2@test.cn" not in emails

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "sales_a2@test.cn", "password": "password123"},
    )
    assert resp.status_code == 401
