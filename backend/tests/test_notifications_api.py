"""通知 API 测试：仅本人可见、标记已读、未读数。"""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification
from app.models.enums import NotificationType
from tests.conftest import RoleUsers

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


async def _seed_notification(session: AsyncSession, user_id: object, title: str) -> Notification:
    n = Notification(
        user_id=user_id,
        type=NotificationType.STALE_NO_FOLLOWUP,
        title=title,
        related_type="opportunity",
    )
    session.add(n)
    await session.commit()
    return n


async def test_notifications_scoped_to_self(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    await _seed_notification(session, roles.sales_a.id, "A 的提醒")
    await _seed_notification(session, roles.sales_b.id, "B 的提醒")

    resp = await client.get("/api/v1/notifications", headers=await login("sales_a@test.cn"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "A 的提醒"

    # manager 也只看到自己的（通知没有团队可见性）
    resp = await client.get("/api/v1/notifications", headers=await login("manager_a@test.cn"))
    assert resp.json()["total"] == 0


async def test_mark_read_and_unread_count(
    client: AsyncClient, session: AsyncSession, roles: RoleUsers, login: LoginFn
) -> None:
    n1 = await _seed_notification(session, roles.sales_a.id, "提醒一")
    await _seed_notification(session, roles.sales_a.id, "提醒二")
    headers = await login("sales_a@test.cn")

    resp = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp.json()["unread"] == 2

    resp = await client.post(f"/api/v1/notifications/{n1.id}/read", headers=headers)
    assert resp.status_code == 204
    resp = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp.json()["unread"] == 1

    # 别人不能标记我的通知
    resp = await client.post(
        f"/api/v1/notifications/{n1.id}/read", headers=await login("sales_b@test.cn")
    )
    assert resp.status_code == 404

    resp = await client.post("/api/v1/notifications/read-all", headers=headers)
    assert resp.status_code == 204
    resp = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert resp.json()["unread"] == 0
