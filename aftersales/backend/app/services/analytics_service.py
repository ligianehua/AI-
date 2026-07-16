"""售后数据分析聚合"""
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    Conversation,
    RmaRequest,
    SatisfactionRating,
    Ticket,
)


def overview(db: Session) -> dict:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    total_convs = db.query(Conversation).count()
    today_convs = db.query(Conversation).filter(Conversation.created_at >= today).count()

    closed = db.query(Conversation).filter(Conversation.status == "closed").count()
    handed = db.query(Conversation).filter(Conversation.handed_off == True).count()  # noqa: E712
    resolved_ai = db.query(Conversation).filter(
        Conversation.status == "closed",
        Conversation.handed_off == False).count()  # noqa: E712

    open_tickets = db.query(Ticket).filter(Ticket.status.notin_(["已关闭"])).count()
    active_rma = db.query(RmaRequest).filter(
        RmaRequest.status.notin_(["已完成", "已驳回", "已取消"])).count()
    avg_score = db.query(func.avg(SatisfactionRating.score)).scalar()

    return {
        "today_conversations": today_convs,
        "total_conversations": total_convs,
        "ai_self_resolve_rate": round(resolved_ai / closed * 100, 1) if closed else None,
        "handoff_rate": round(handed / total_convs * 100, 1) if total_convs else None,
        "open_tickets": open_tickets,
        "active_rma": active_rma,
        "avg_satisfaction": round(float(avg_score), 2) if avg_score else None,
    }


def trends(db: Session, days: int = 30) -> dict:
    since = datetime.now() - timedelta(days=days - 1)
    since = since.replace(hour=0, minute=0, second=0, microsecond=0)
    labels = [(since + timedelta(days=i)).strftime("%m-%d") for i in range(days)]

    def bucket(rows, get_dt):
        counts = {l: 0 for l in labels}
        for r in rows:
            key = get_dt(r).strftime("%m-%d")
            if key in counts:
                counts[key] += 1
        return [counts[l] for l in labels]

    convs = db.query(Conversation).filter(Conversation.created_at >= since).all()
    tickets = db.query(Ticket).filter(Ticket.created_at >= since).all()
    ratings = db.query(SatisfactionRating).filter(SatisfactionRating.created_at >= since).all()

    score_sum = {l: [0, 0] for l in labels}
    for r in ratings:
        key = r.created_at.strftime("%m-%d")
        if key in score_sum:
            score_sum[key][0] += r.score
            score_sum[key][1] += 1
    scores = [round(s / n, 2) if n else None for s, n in (score_sum[l] for l in labels)]

    return {
        "labels": labels,
        "conversations": bucket(convs, lambda r: r.created_at),
        "tickets": bucket(tickets, lambda r: r.created_at),
        "satisfaction": scores,
    }


def distribution(db: Session) -> dict:
    ticket_status = dict(db.query(Ticket.status, func.count(Ticket.id))
                         .group_by(Ticket.status).all())
    ticket_category = dict(db.query(Ticket.category, func.count(Ticket.id))
                           .group_by(Ticket.category).all())
    rma_type = dict(db.query(RmaRequest.type, func.count(RmaRequest.id))
                    .group_by(RmaRequest.type).all())
    score_dist = dict(db.query(SatisfactionRating.score, func.count(SatisfactionRating.id))
                      .group_by(SatisfactionRating.score).all())
    return {
        "ticket_status": ticket_status,
        "ticket_category": ticket_category,
        "rma_type": rma_type,
        "satisfaction_dist": {str(k): v for k, v in score_dist.items()},
    }
