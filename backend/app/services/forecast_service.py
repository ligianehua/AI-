"""M11 销售预测：加权 pipeline + 周度快照 + 外推（数据量守卫）。

诚实红线（PLAN §6.9）：快照 < MIN_TREND_WEEKS 周时 trend=None，只展示 pipeline 与
历史走势；外推是最小二乘线性回归 + 残差 95% 区间，method 与数据量全部随响应返回。
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezone import biz_today
from app.models.enums import OpportunityStage
from app.models.forecast_snapshot import ForecastSnapshot
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.base import visibility_scope

OPEN_STAGES = (
    OpportunityStage.INITIAL,
    OpportunityStage.NEED_CONFIRMED,
    OpportunityStage.PROPOSAL,
    OpportunityStage.NEGOTIATION,
)

MIN_TREND_WEEKS = 26  # 约 2 个完整季度；不足不做时序外推
SNAPSHOT_WINDOW = 26  # 响应返回的历史快照条数上限（周）


# ---------- 加权 pipeline ----------


async def weighted_pipeline(session: AsyncSession, actor: User) -> dict[str, Any]:
    """当前进行中商机的加权 pipeline（按可见域）。"""
    stmt: Select[tuple[Opportunity]] = select(Opportunity).where(
        Opportunity.deleted_at.is_(None),
        Opportunity.stage.in_([s.value for s in OPEN_STAGES]),
    )
    stmt = visibility_scope(stmt, Opportunity, actor)
    opps = list(await session.scalars(stmt))

    by_stage: dict[str, dict[str, Any]] = {
        s.value: {"stage": s.value, "amount": Decimal(0), "weighted": Decimal(0), "count": 0}
        for s in OPEN_STAGES
    }
    for opp in opps:
        bucket = by_stage[opp.stage]
        bucket["amount"] += opp.amount
        bucket["weighted"] += opp.amount * opp.probability / 100
        bucket["count"] += 1

    total = sum((b["amount"] for b in by_stage.values()), Decimal(0))
    weighted = sum((b["weighted"] for b in by_stage.values()), Decimal(0))
    return {
        "total_amount": float(total),
        "weighted_amount": float(round(weighted, 2)),
        "open_count": len(opps),
        "by_stage": [
            {
                "stage": b["stage"],
                "amount": float(b["amount"]),
                "weighted": float(round(b["weighted"], 2)),
                "count": b["count"],
            }
            for b in by_stage.values()
        ],
    }


# ---------- 快照（按 owner 粒度全量生成，读取时按可见域聚合） ----------


async def take_snapshots(session: AsyncSession, snapshot_date: date | None = None) -> int:
    """为每个有进行中商机的 owner 生成当日快照（同日重跑覆盖，幂等）。返回快照条数。"""
    snapshot_date = snapshot_date or biz_today()
    rows = (
        await session.execute(
            select(
                Opportunity.owner_id,
                Opportunity.stage,
                func.sum(Opportunity.amount),
                func.sum(Opportunity.amount * Opportunity.probability / 100),
                func.count(),
            )
            .where(
                Opportunity.deleted_at.is_(None),
                Opportunity.stage.in_([s.value for s in OPEN_STAGES]),
            )
            .group_by(Opportunity.owner_id, Opportunity.stage)
        )
    ).all()

    per_owner: dict[uuid.UUID, dict[str, Any]] = {}
    for owner_id, stage, amount, weighted, count in rows:
        agg = per_owner.setdefault(
            owner_id,
            {"total": Decimal(0), "weighted": Decimal(0), "count": 0, "by_stage": {}},
        )
        agg["total"] += amount
        agg["weighted"] += weighted
        agg["count"] += int(count)
        agg["by_stage"][stage] = {"amount": float(amount), "weighted": float(weighted)}

    for owner_id, agg in per_owner.items():
        insert_stmt = pg_insert(ForecastSnapshot).values(
            snapshot_date=snapshot_date,
            owner_id=owner_id,
            total_amount=agg["total"],
            weighted_amount=round(agg["weighted"], 2),
            open_count=agg["count"],
            by_stage=agg["by_stage"],
        )
        await session.execute(
            insert_stmt.on_conflict_do_update(
                index_elements=["owner_id", "snapshot_date"],
                index_where=ForecastSnapshot.deleted_at.is_(None),
                set_={
                    "total_amount": insert_stmt.excluded.total_amount,
                    "weighted_amount": insert_stmt.excluded.weighted_amount,
                    "open_count": insert_stmt.excluded.open_count,
                    "by_stage": insert_stmt.excluded.by_stage,
                    "updated_at": func.now(),
                },
            )
        )
    await session.commit()
    return len(per_owner)


async def snapshot_history(session: AsyncSession, actor: User) -> list[dict[str, Any]]:
    """可见域内快照按日期聚合（近 SNAPSHOT_WINDOW 期）。"""
    stmt = (
        select(
            ForecastSnapshot.snapshot_date,
            func.sum(ForecastSnapshot.total_amount),
            func.sum(ForecastSnapshot.weighted_amount),
        )
        .where(ForecastSnapshot.deleted_at.is_(None))
        .group_by(ForecastSnapshot.snapshot_date)
        .order_by(ForecastSnapshot.snapshot_date.desc())
        .limit(SNAPSHOT_WINDOW)
    )
    stmt = visibility_scope(stmt, ForecastSnapshot, actor)  # type: ignore[arg-type, assignment]
    rows = (await session.execute(stmt)).all()
    return [
        {"date": d.isoformat(), "total_amount": float(t), "weighted_amount": float(w)}
        for d, t, w in reversed(rows)
    ]


# ---------- 外推（数据量守卫 + 最小二乘） ----------


def linear_trend(points: list[float]) -> dict[str, float] | None:
    """最小二乘外推下一期，95% 区间用残差标准差近似。纯函数便于单测。"""
    n = len(points)
    if n < MIN_TREND_WEEKS:
        return None
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(points) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, points, strict=True)) / denom
    intercept = mean_y - slope * mean_x
    residuals = [y - (slope * x + intercept) for x, y in zip(xs, points, strict=True)]
    sigma = (sum(r**2 for r in residuals) / max(1, n - 2)) ** 0.5
    next_value = slope * n + intercept
    return {
        "next_weighted": round(next_value, 2),
        "lower": round(next_value - 1.96 * sigma, 2),
        "upper": round(next_value + 1.96 * sigma, 2),
        "slope_per_period": round(slope, 2),
    }


async def forecast_overview(session: AsyncSession, actor: User) -> dict[str, Any]:
    pipeline = await weighted_pipeline(session, actor)
    history = await snapshot_history(session, actor)
    trend = linear_trend([h["weighted_amount"] for h in history])
    weeks = len(history)
    if trend is None:
        data_note = (
            f"已积累 {weeks} 期快照，不足 {MIN_TREND_WEEKS} 期（约 2 个完整季度），"
            "暂不做时序外推——当前仅展示加权 pipeline 与历史走势。"
        )
    else:
        data_note = f"基于 {weeks} 期快照的线性外推，区间为残差 95% 置信近似，仅供参考。"
    return {
        "pipeline": pipeline,
        "snapshots": history,
        "trend": {**trend, "method": "least_squares"} if trend else None,
        "data_note": data_note,
    }
