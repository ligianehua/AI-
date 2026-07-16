"""主动提醒引擎：定时扫描生成 保修到期/保养周期/差评回访 提醒；RMA 状态变化即时推送。

从"被动响应"到"主动服务"的落点。dedup_key 保证同一事项只提醒一次。
"""
import asyncio
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import (
    Conversation,
    Order,
    Reminder,
    SatisfactionRating,
    Ticket,
)

WARRANTY_WINDOW_DAYS = 30  # 保修到期前30天提醒

# 保养周期规则：类目 -> (周期天数, 提醒文案)
MAINTENANCE_RULES = {
    "空气净化器": (180, "您的空气净化器滤芯已使用约 6 个月，为保证净化效果建议检查并更换滤芯（商城搜索\"A3滤芯\"，会员9折）。"),
    "扫地机器人": (90, "您的扫地机器人已使用约 3 个月，建议清洗高效滤网、清理主刷缠发，并检查边刷是否变形。"),
    "电动牙刷": (90, "您的电动牙刷刷头已使用约 3 个月，牙医建议每 3 个月更换刷头以保证清洁效果。"),
    "智能门锁": (300, "您的智能门锁电池已使用约 10 个月，临近常规续航上限，建议备好 8 节 5 号碱性电池及时更换。"),
}


def _add(db: Session, *, customer_id: int | None, audience: str, rtype: str,
         title: str, content: str, related_no: str | None, dedup_key: str) -> bool:
    if db.query(Reminder).filter(Reminder.dedup_key == dedup_key).first():
        return False
    db.add(Reminder(customer_id=customer_id, audience=audience, type=rtype,
                    title=title, content=content, related_no=related_no,
                    dedup_key=dedup_key))
    return True


def notify_rma_update(db: Session, rma, note: str = ""):
    """RMA 状态变化即时通知客户（rma_service.transition 调用）"""
    _add(db, customer_id=rma.customer_id, audience="customer", rtype="rma_update",
         title=f"售后进度更新：{rma.type}单 {rma.rma_no} → {rma.status}",
         content=(f"您的{rma.type}申请 {rma.rma_no}（{rma.order.product.name}）"
                  f"状态已更新为「{rma.status}」。" + (f" {note}" if note else "")),
         related_no=rma.rma_no, dedup_key=f"rma:{rma.rma_no}:{rma.status}")


def scan(db: Session) -> dict:
    """全量扫描，返回各类新增数量"""
    now = datetime.now()
    created = {"warranty": 0, "maintenance": 0, "followup": 0}

    orders = db.query(Order).filter(Order.delivered_at.isnot(None)).all()
    for o in orders:
        p = o.product
        delivered = o.delivered_at
        # 1) 保修到期提醒
        warranty_end = delivered + timedelta(days=p.warranty_months * 30)
        days_left = (warranty_end - now).days
        if 0 < days_left <= WARRANTY_WINDOW_DAYS:
            if _add(db, customer_id=o.customer_id, audience="customer",
                    rtype="warranty_expiry",
                    title=f"保修即将到期：{p.name}",
                    content=(f"您的 {p.name}（订单 {o.order_no}）保修将于 "
                             f"{warranty_end:%Y-%m-%d} 到期（剩余 {days_left} 天）。"
                             f"如设备有任何异常，建议在保修期内尽快申请免费检测维修。"),
                    related_no=o.order_no, dedup_key=f"warranty:{o.order_no}"):
                created["warranty"] += 1
        # 2) 保养周期提醒
        rule = MAINTENANCE_RULES.get(p.category)
        if rule:
            cycle_days, tip = rule
            used_days = (now - delivered).days
            if used_days >= cycle_days:
                cycle_no = used_days // cycle_days  # 每个周期提醒一次
                if _add(db, customer_id=o.customer_id, audience="customer",
                        rtype="maintenance",
                        title=f"保养提醒：{p.name}",
                        content=tip, related_no=o.order_no,
                        dedup_key=f"maint:{o.order_no}:{cycle_no}"):
                    created["maintenance"] += 1

    # 3) 差评自动回访：评分<=2 生成高优回访工单 + 内部任务
    low_ratings = db.query(SatisfactionRating).filter(SatisfactionRating.score <= 2).all()
    for r in low_ratings:
        dedup = f"followup:conv:{r.conversation_id}"
        if db.query(Reminder).filter(Reminder.dedup_key == dedup).first():
            continue
        conv = db.query(Conversation).get(r.conversation_id)
        from . import ticket_service
        ticket = ticket_service.create_ticket(
            db, customer_id=r.customer_id,
            title=f"【差评回访】客户 {r.score} 星评价，48小时内回访",
            description=(f"会话 #{r.conversation_id}（{conv.title if conv else ''}）"
                         f"获得 {r.score} 星评价。评价内容：{r.comment or '（无）'}\n"
                         f"请客服 48 小时内电话/在线回访，安抚客户并跟进问题。"),
            category="投诉建议", priority="高",
            conversation_id=r.conversation_id, operator="提醒引擎")
        _add(db, customer_id=r.customer_id, audience="staff", rtype="low_rating_followup",
             title=f"差评回访任务：{r.score} 星（会话 #{r.conversation_id}）",
             content=f"已自动创建回访工单 {ticket.ticket_no}，请尽快跟进。",
             related_no=ticket.ticket_no, dedup_key=dedup)
        created["followup"] += 1

    # 4) 热点预警：近7天某问题标签出现>=3次且上升 -> 运营内部任务
    from . import learning_service
    week = now.strftime("%Y-W%W")
    for item in learning_service.hot_issue_tags(db, days=7):
        if item["count"] >= 3 and item["trend"] != "down":
            if _add(db, customer_id=None, audience="staff", rtype="hot_issue_alert",
                    title=f"热点预警：「{item['tag']}」近7天出现 {item['count']} 次",
                    content=(f"问题标签「{item['tag']}」近 7 天出现 {item['count']} 次"
                             f"（上一周期 {item['prev']} 次）。建议知识运营检查相关知识覆盖，"
                             f"必要时联动产品/品控排查批次问题。"),
                    related_no=None, dedup_key=f"hot:{item['tag']}:{week}"):
                created.setdefault("hot_alert", 0)
                created["hot_alert"] += 1

    db.commit()
    return created


async def auto_learning_loop():
    """学习分析自动化：每小时检查，距上次完成超过 AUTO_ANALYZE_HOURS 且有待分析会话则自动跑"""
    import asyncio as _asyncio
    from datetime import timedelta as _td

    from ..config import settings
    from ..database import SessionLocal
    from ..models import AnalysisRun, Conversation as _Conv
    from . import learning_service

    await _asyncio.sleep(60)
    while True:
        db = SessionLocal()
        try:
            running = db.query(AnalysisRun).filter(AnalysisRun.status == "running").first()
            last_done = db.query(AnalysisRun).filter(AnalysisRun.status == "done") \
                .order_by(AnalysisRun.id.desc()).first()
            pending = db.query(_Conv).filter(_Conv.status == "closed",
                                             _Conv.analyzed == False).count()  # noqa: E712
            due = (last_done is None or
                   datetime.now() - (last_done.finished_at or last_done.started_at)
                   >= _td(hours=settings.auto_analyze_hours))
            if not running and pending > 0 and due:
                run = AnalysisRun(trigger="auto")
                db.add(run)
                db.commit()
                run_id = run.id
                db.close()
                await _asyncio.to_thread(learning_service.run_analysis, run_id)
            else:
                db.close()
        except Exception:
            try:
                db.rollback()
                db.close()
            except Exception:
                pass
        await _asyncio.sleep(3600)


async def periodic_scan(interval_seconds: int = 1800):
    """后台循环：启动 15 秒后首扫，之后每 interval 一轮"""
    from ..database import SessionLocal
    await asyncio.sleep(15)
    while True:
        db = SessionLocal()
        try:
            scan(db)
        except Exception:
            db.rollback()
        finally:
            db.close()
        await asyncio.sleep(interval_seconds)
