"""商机业务逻辑：CRUD / 看板 / 阶段流转。RBAC 在本层强制。"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.models.account import Account
from app.models.activity import Activity
from app.models.enums import (
    STAGE_DEFAULT_PROBABILITY,
    ActivityRelatedType,
    OpportunityStage,
)
from app.models.opportunity import Opportunity
from app.models.user import User
from app.schemas.opportunity import (
    KanbanColumn,
    KanbanResponse,
    OpportunityCreate,
    OpportunityOut,
    OpportunityUpdate,
    StageChangeRequest,
)
from app.services.account_service import account_service
from app.services.base import BaseService

STAGE_LABELS = {
    OpportunityStage.INITIAL: "初步接触",
    OpportunityStage.NEED_CONFIRMED: "需求确认",
    OpportunityStage.PROPOSAL: "方案报价",
    OpportunityStage.NEGOTIATION: "商务谈判",
    OpportunityStage.WON: "赢单",
    OpportunityStage.LOST: "输单",
}


class OpportunityService(BaseService[Opportunity]):
    model = Opportunity
    sortable_fields = frozenset({"created_at", "amount", "expected_close_date"})


opportunity_service = OpportunityService()


def _history_entry(stage: OpportunityStage, by: str) -> dict[str, str]:
    return {"stage": stage.value, "entered_at": datetime.now(UTC).isoformat(), "by": by}


def stage_entered_at(opp: Opportunity) -> datetime:
    """当前阶段的进入时间（stage_history 最后一条；无则商机创建时间）。"""
    if opp.stage_history:
        try:
            return datetime.fromisoformat(opp.stage_history[-1]["entered_at"])
        except (KeyError, ValueError):
            pass
    return opp.created_at


def stuck_days(opp: Opportunity, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    return max(0, (now - stage_entered_at(opp)).days)


async def create_opportunity(
    session: AsyncSession, actor: User, payload: OpportunityCreate
) -> Opportunity:
    await account_service.get(session, actor, payload.account_id)  # 可见域校验
    opp = Opportunity(
        **payload.model_dump(),
        stage=OpportunityStage.INITIAL,
        probability=STAGE_DEFAULT_PROBABILITY[OpportunityStage.INITIAL],
        owner_id=actor.id,
        stage_history=[_history_entry(OpportunityStage.INITIAL, actor.name)],
    )
    session.add(opp)
    await session.commit()
    await session.refresh(opp)
    return opp


async def update_opportunity(
    session: AsyncSession, actor: User, opportunity_id: uuid.UUID, payload: OpportunityUpdate
) -> Opportunity:
    opp = await opportunity_service.get(session, actor, opportunity_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(opp, key, value)
    await session.commit()
    await session.refresh(opp)
    return opp


async def change_stage(
    session: AsyncSession, actor: User, opportunity_id: uuid.UUID, payload: StageChangeRequest
) -> Opportunity:
    """换阶段：记 stage_history；won 必须确认金额，lost 必须填原因（预测与归因的数据原料）。"""
    opp = await opportunity_service.get(session, actor, opportunity_id)
    if payload.stage == opp.stage:
        raise DomainError("商机已处于该阶段")
    if payload.stage == OpportunityStage.WON:
        if payload.amount is None:
            raise DomainError("赢单必须确认成交金额")
        opp.amount = payload.amount
    if payload.stage == OpportunityStage.LOST:
        if not payload.lost_reason or not payload.lost_reason.strip():
            raise DomainError("输单必须填写原因")
        opp.lost_reason = payload.lost_reason.strip()

    opp.stage = payload.stage
    opp.probability = STAGE_DEFAULT_PROBABILITY[payload.stage]
    opp.stage_history = [*opp.stage_history, _history_entry(payload.stage, actor.name)]
    await session.commit()
    await session.refresh(opp)
    return opp


async def _last_activity_map(
    session: AsyncSession, opportunity_ids: list[uuid.UUID]
) -> dict[uuid.UUID, datetime]:
    if not opportunity_ids:
        return {}
    rows = (
        await session.execute(
            select(Activity.related_id, func.max(Activity.created_at))
            .where(
                Activity.related_type == ActivityRelatedType.OPPORTUNITY,
                Activity.related_id.in_(opportunity_ids),
                Activity.deleted_at.is_(None),
            )
            .group_by(Activity.related_id)
        )
    ).all()
    return {row[0]: row[1] for row in rows}


def _to_out(
    opp: Opportunity,
    account_name: str,
    owner_name: str,
    last_activity: datetime | None,
) -> OpportunityOut:
    out = OpportunityOut.model_validate(opp)
    out.account_name = account_name
    out.owner_name = owner_name
    out.stuck_days = stuck_days(opp)
    out.last_activity_at = last_activity
    return out


async def get_kanban(session: AsyncSession, actor: User) -> KanbanResponse:
    """按阶段分组的看板：每列含金额汇总与加权金额（Σ 金额 × 概率）。"""
    rows = (
        await session.execute(
            opportunity_service.base_query(actor)
            .add_columns(Account.name, User.name)
            .join(Account, Account.id == Opportunity.account_id)
            .join(User, User.id == Opportunity.owner_id)
            .order_by(Opportunity.created_at.desc())
        )
    ).all()
    last_map = await _last_activity_map(session, [row[0].id for row in rows])

    grouped: dict[OpportunityStage, list[OpportunityOut]] = {s: [] for s in OpportunityStage}
    for opp, account_name, owner_name in rows:
        grouped[OpportunityStage(opp.stage)].append(
            _to_out(opp, account_name, owner_name, last_map.get(opp.id))
        )

    columns = []
    for stage in OpportunityStage:
        items = grouped[stage]
        total = sum(Decimal(str(i.amount)) for i in items)
        weighted = sum(Decimal(str(i.amount)) * i.probability / 100 for i in items)
        columns.append(
            KanbanColumn(
                stage=stage,
                total_amount=float(total),
                weighted_amount=float(weighted),
                items=items,
            )
        )
    return KanbanResponse(columns=columns)


async def get_opportunity_out(
    session: AsyncSession, actor: User, opportunity_id: uuid.UUID
) -> OpportunityOut:
    opp = await opportunity_service.get(session, actor, opportunity_id)
    account_name = await session.scalar(select(Account.name).where(Account.id == opp.account_id))
    owner_name = await session.scalar(select(User.name).where(User.id == opp.owner_id))
    last_map = await _last_activity_map(session, [opp.id])
    return _to_out(opp, account_name or "", owner_name or "", last_map.get(opp.id))
