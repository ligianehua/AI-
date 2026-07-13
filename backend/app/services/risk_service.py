"""风险扫描（每日 08:00 定时任务的执行体）。

三种风险（PLAN §6.3，与 notifications.type 一一对应）：
- stale_no_followup：商机 > N 天无跟进（默认 7，配置化）
- stage_stuck：阶段停滞 > M 天（默认 21）
- next_action_due：跟进记录的 next_action_date 到期未处理（近 7 天窗口）

now 由调用方注入（测试用固定时间即"时间 mock"）；按未读通知去重，避免每日轰炸。
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timezone import biz_today
from app.models.activity import Activity
from app.models.enums import ActivityRelatedType, NotificationType, OpportunityStage
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.services.opportunity_service import stage_entered_at


async def _has_unread(
    session: AsyncSession,
    user_id: object,
    ntype: NotificationType,
    related_type: str,
    related_id: object,
) -> bool:
    return bool(
        await session.scalar(
            select(
                exists().where(
                    Notification.user_id == user_id,
                    Notification.type == ntype,
                    Notification.related_type == related_type,
                    Notification.related_id == related_id,
                    Notification.read_at.is_(None),
                    Notification.deleted_at.is_(None),
                )
            )
        )
    )


async def scan_risks(session: AsyncSession, now: datetime | None = None) -> int:
    """扫描全量未关闭商机与到期 next_action，写入 notifications。返回新增通知数。"""
    now = now or datetime.now(UTC)
    settings = get_settings()
    created = 0

    open_opps = list(
        await session.scalars(
            select(Opportunity).where(
                Opportunity.deleted_at.is_(None),
                Opportunity.stage.notin_([OpportunityStage.WON, OpportunityStage.LOST]),
            )
        )
    )
    last_activity_rows = (
        await session.execute(
            select(Activity.related_id, func.max(Activity.created_at))
            .where(
                Activity.related_type == ActivityRelatedType.OPPORTUNITY,
                Activity.related_id.in_([o.id for o in open_opps] or [None]),
                Activity.deleted_at.is_(None),
            )
            .group_by(Activity.related_id)
        )
    ).all()
    last_map = {row[0]: row[1] for row in last_activity_rows}

    for opp in open_opps:
        last_touch = last_map.get(opp.id) or opp.created_at
        stale_days = (now - last_touch).days
        if stale_days > settings.risk_stale_days and not await _has_unread(
            session, opp.owner_id, NotificationType.STALE_NO_FOLLOWUP, "opportunity", opp.id
        ):
            session.add(
                Notification(
                    user_id=opp.owner_id,
                    type=NotificationType.STALE_NO_FOLLOWUP,
                    title=f"商机「{opp.name}」已 {stale_days} 天无跟进",
                    body="长期无跟进的商机成交率会快速衰减，建议尽快联系客户。",
                    related_type="opportunity",
                    related_id=opp.id,
                )
            )
            created += 1

        stuck = (now - stage_entered_at(opp)).days
        if stuck > settings.risk_stuck_days and not await _has_unread(
            session, opp.owner_id, NotificationType.STAGE_STUCK, "opportunity", opp.id
        ):
            session.add(
                Notification(
                    user_id=opp.owner_id,
                    type=NotificationType.STAGE_STUCK,
                    title=f"商机「{opp.name}」在当前阶段停滞 {stuck} 天",
                    body="阶段长期不推进，建议评估卡点或调整策略。",
                    related_type="opportunity",
                    related_id=opp.id,
                )
            )
            created += 1

    # next_action 到期未处理（近 7 天窗口，避免历史数据轰炸；Asia/Shanghai 日界）
    today = biz_today(now)
    due_activities = list(
        await session.scalars(
            select(Activity).where(
                Activity.deleted_at.is_(None),
                Activity.next_action.is_not(None),
                Activity.next_action_date.is_not(None),
                Activity.next_action_date <= today,
                Activity.next_action_date >= today - timedelta(days=7),
            )
        )
    )
    for activity in due_activities:
        # 去重键与写入键必须一致（按 activity 粒度），否则未读去重失效导致每日重复提醒
        if await _has_unread(
            session, activity.owner_id, NotificationType.NEXT_ACTION_DUE, "activity", activity.id
        ):
            continue
        session.add(
            Notification(
                user_id=activity.owner_id,
                type=NotificationType.NEXT_ACTION_DUE,
                title=f"下一步行动到期：{activity.next_action}",
                body=f"计划日期 {activity.next_action_date}，请确认是否已完成。",
                related_type="activity",
                related_id=activity.id,
            )
        )
        created += 1

    await session.commit()
    return created
