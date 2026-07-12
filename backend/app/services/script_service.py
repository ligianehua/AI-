"""话术库：admin/manager 管理，全员可读可检索。创建/改内容后异步重嵌入。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.enums import Role, ScriptCategory
from app.models.script import Script
from app.models.user import User
from app.schemas.script import ScriptCreate, ScriptOut, ScriptUpdate
from app.tasks import dispatcher


def _require_manager(actor: User) -> None:
    if actor.role not in (Role.ADMIN, Role.MANAGER):
        raise PermissionDeniedError("话术库管理仅限主管和管理员")


def to_out(script: Script) -> ScriptOut:
    out = ScriptOut.model_validate(script)
    out.has_embedding = script.embedding is not None
    return out


async def list_scripts(
    session: AsyncSession,
    actor: User,
    *,
    category: ScriptCategory | None = None,
    include_inactive: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Script], int]:
    stmt = select(Script).where(Script.deleted_at.is_(None))
    if category:
        stmt = stmt.where(Script.category == category)
    if not include_inactive:
        stmt = stmt.where(Script.is_active.is_(True))
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = await session.scalars(
        stmt.order_by(Script.created_at.desc()).limit(page_size).offset((page - 1) * page_size)
    )
    return list(rows), total


async def create_script(session: AsyncSession, actor: User, payload: ScriptCreate) -> Script:
    _require_manager(actor)
    script = Script(**payload.model_dump(), created_by=actor.id, is_active=True)
    session.add(script)
    await session.commit()
    await session.refresh(script)
    await dispatcher.enqueue("embed_script_task", str(script.id))
    return script


async def _get_script(session: AsyncSession, script_id: uuid.UUID) -> Script:
    script = await session.scalar(
        select(Script).where(Script.id == script_id, Script.deleted_at.is_(None))
    )
    if script is None:
        raise NotFoundError("话术不存在")
    return script


async def update_script(
    session: AsyncSession, actor: User, script_id: uuid.UUID, payload: ScriptUpdate
) -> Script:
    _require_manager(actor)
    script = await _get_script(session, script_id)
    data = payload.model_dump(exclude_unset=True)
    content_changed = "content" in data and data["content"] != script.content
    for key, value in data.items():
        setattr(script, key, value)
    if content_changed:
        script.embedding = None  # 旧向量失效
    await session.commit()
    await session.refresh(script)
    if content_changed:
        await dispatcher.enqueue("embed_script_task", str(script.id))
    return script


async def delete_script(session: AsyncSession, actor: User, script_id: uuid.UUID) -> None:
    _require_manager(actor)
    script = await _get_script(session, script_id)
    script.deleted_at = datetime.now(UTC)
    script.is_active = False
    await session.commit()


async def bump_usage(session: AsyncSession, script_ids: list[uuid.UUID]) -> None:
    """推荐引用后累计使用次数。"""
    if not script_ids:
        return
    rows = await session.scalars(select(Script).where(Script.id.in_(script_ids)))
    for script in rows:
        script.usage_count += 1
    await session.commit()
