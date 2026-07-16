"""工单状态机与业务操作"""
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Ticket, TicketEvent

# 合法状态迁移表
TRANSITIONS: dict[str, list[str]] = {
    "待处理": ["处理中", "已关闭"],
    "处理中": ["待客户确认", "已关闭"],
    "待客户确认": ["已解决", "处理中"],
    "已解决": ["已关闭", "处理中"],
    "已关闭": [],
}


class InvalidTransition(Exception):
    pass


def gen_ticket_no(db: Session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"TK{today}-"
    last = db.query(Ticket.ticket_no).filter(Ticket.ticket_no.like(f"{prefix}%")) \
        .order_by(Ticket.ticket_no.desc()).first()
    seq = int(last[0].rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{seq:04d}"


def create_ticket(db: Session, *, customer_id: int, title: str, description: str = "",
                  category: str = "其他", priority: str = "中",
                  conversation_id: int | None = None, order_id: int | None = None,
                  operator: str = "AI助手") -> Ticket:
    ticket = Ticket(
        ticket_no=gen_ticket_no(db), customer_id=customer_id, title=title[:200],
        description=description, category=category, priority=priority,
        conversation_id=conversation_id, order_id=order_id, status="待处理",
    )
    db.add(ticket)
    db.flush()
    db.add(TicketEvent(ticket_id=ticket.id, from_status=None, to_status="待处理",
                       note="工单创建", operator=operator))
    return ticket


def transition(db: Session, ticket: Ticket, to_status: str,
               note: str = "", operator: str = "客服") -> Ticket:
    allowed = TRANSITIONS.get(ticket.status, [])
    if to_status not in allowed:
        raise InvalidTransition(
            f"工单 {ticket.ticket_no} 不能从「{ticket.status}」变为「{to_status}」，"
            f"允许的下一状态：{allowed or '（终态）'}")
    from_status = ticket.status
    ticket.status = to_status
    ticket.updated_at = datetime.now()
    if to_status == "已解决":
        ticket.resolved_at = datetime.now()
    db.add(TicketEvent(ticket_id=ticket.id, from_status=from_status,
                       to_status=to_status, note=note, operator=operator))
    return ticket


def add_note(db: Session, ticket: Ticket, note: str, operator: str = "客服"):
    db.add(TicketEvent(ticket_id=ticket.id, from_status=ticket.status,
                       to_status=ticket.status, note=note, operator=operator))
    ticket.updated_at = datetime.now()
