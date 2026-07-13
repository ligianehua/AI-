"""通用 CRUD service 基类 + RBAC 可见域过滤。

硬性规则：任何业务查询必须经过 visibility_scope（sales=本人 / manager=本团队 / admin=全量），
禁止在路由层裸查。
"""

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.exceptions import DomainError, NotFoundError
from app.models.base import AppModel
from app.models.enums import Role
from app.models.user import User


def visibility_scope[M: AppModel](
    stmt: Select[tuple[M]], model: type[M], actor: User, owner_field: str = "owner_id"
) -> Select[tuple[M]]:
    """按角色收窄可见范围：sales=本人，manager=本团队，admin=全量。"""
    if actor.role == Role.ADMIN:
        return stmt
    owner_col: InstrumentedAttribute[uuid.UUID] = getattr(model, owner_field)
    if actor.role == Role.MANAGER and actor.team_id is not None:
        # 不排除已软删用户：离职销售名下的客户/商机必须保留在团队视图中
        team_members = select(User.id).where(User.team_id == actor.team_id)
        return stmt.where(owner_col.in_(team_members))
    return stmt.where(owner_col == actor.id)


class BaseService[M: AppModel]:
    """列表/详情的通用实现：软删过滤 + 可见域 + 分页 + 排序白名单。"""

    model: type[M]
    owner_field: str | None = "owner_id"
    sortable_fields: frozenset[str] = frozenset({"created_at"})

    def base_query(self, actor: User) -> Select[tuple[M]]:
        stmt = select(self.model).where(self.model.deleted_at.is_(None))
        if self.owner_field is not None:
            stmt = visibility_scope(stmt, self.model, actor, self.owner_field)
        return stmt

    def apply_sort(self, stmt: Select[tuple[M]], sort: str | None) -> Select[tuple[M]]:
        if not sort:
            return stmt.order_by(self.model.created_at.desc())
        field = sort.removeprefix("-")
        if field not in self.sortable_fields:
            raise DomainError(f"不支持的排序字段：{field}")
        col = getattr(self.model, field)
        return stmt.order_by(col.desc() if sort.startswith("-") else col.asc())

    async def paginate(
        self, session: AsyncSession, stmt: Select[tuple[M]], page: int, page_size: int
    ) -> tuple[list[M], int]:
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total = await session.scalar(count_stmt)
        rows = await session.scalars(stmt.limit(page_size).offset((page - 1) * page_size))
        return list(rows), int(total or 0)

    async def list(
        self,
        session: AsyncSession,
        actor: User,
        page: int = 1,
        page_size: int = 20,
        sort: str | None = None,
    ) -> tuple[list[M], int]:
        stmt = self.apply_sort(self.base_query(actor), sort)
        return await self.paginate(session, stmt, page, page_size)

    async def get(self, session: AsyncSession, actor: User, obj_id: uuid.UUID) -> M:
        obj = await session.scalar(self.base_query(actor).where(self.model.id == obj_id))
        if obj is None:
            raise NotFoundError("记录不存在或无权访问")
        return obj
