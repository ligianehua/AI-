from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from tests.conftest import RoleUsers

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


async def test_admin_team_crud(client: AsyncClient, roles: RoleUsers, login: LoginFn) -> None:
    headers = await login("admin@test.cn")

    resp = await client.post("/api/v1/teams", json={"name": "华南销售部"}, headers=headers)
    assert resp.status_code == 201
    team_id = resp.json()["id"]

    resp = await client.get("/api/v1/teams", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 3

    resp = await client.patch(
        f"/api/v1/teams/{team_id}", json={"name": "华南大区"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "华南大区"

    resp = await client.delete(f"/api/v1/teams/{team_id}", headers=headers)
    assert resp.status_code == 204

    resp = await client.get("/api/v1/teams", headers=headers)
    assert resp.json()["total"] == 2


async def test_create_duplicate_team_name(
    client: AsyncClient, roles: RoleUsers, login: LoginFn
) -> None:
    headers = await login("admin@test.cn")
    resp = await client.post("/api/v1/teams", json={"name": "华东测试团队"}, headers=headers)
    assert resp.status_code == 409


async def test_delete_team_with_members_rejected(
    client: AsyncClient, roles: RoleUsers, login: LoginFn
) -> None:
    headers = await login("admin@test.cn")
    resp = await client.delete(f"/api/v1/teams/{roles.team_a.id}", headers=headers)
    assert resp.status_code == 400
    assert "成员" in resp.json()["message"]


@pytest.mark.parametrize("email", ["manager_a@test.cn", "sales_a@test.cn"])
async def test_non_admin_cannot_manage_teams(
    client: AsyncClient, roles: RoleUsers, login: LoginFn, email: str
) -> None:
    headers = await login(email)
    resp = await client.get("/api/v1/teams", headers=headers)
    assert resp.status_code == 403
    resp = await client.post("/api/v1/teams", json={"name": "偷建团队"}, headers=headers)
    assert resp.status_code == 403
