"""工单路由"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, Ticket, TicketEvent
from ..services import ticket_service

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


def _row(t: Ticket, customer_name: str | None = None) -> dict:
    return {
        "id": t.id, "ticket_no": t.ticket_no, "title": t.title,
        "description": t.description, "category": t.category,
        "priority": t.priority, "status": t.status,
        "customer_id": t.customer_id, "customer_name": customer_name,
        "conversation_id": t.conversation_id, "assignee": t.assignee,
        "created_at": t.created_at.strftime("%Y-%m-%d %H:%M"),
        "updated_at": t.updated_at.strftime("%Y-%m-%d %H:%M"),
        "next_statuses": ticket_service.TRANSITIONS.get(t.status, []),
    }


class CreateTicket(BaseModel):
    customer_id: int
    title: str
    description: str = ""
    category: str = "其他"
    priority: str = "中"


class PatchTicket(BaseModel):
    status: str | None = None
    note: str | None = None
    assignee: str | None = None
    priority: str | None = None


@router.get("")
def list_tickets(status: str | None = None, category: str | None = None,
                 keyword: str | None = None, page: int = 1, size: int = 100,
                 db: Session = Depends(get_db)):
    q = db.query(Ticket).order_by(Ticket.updated_at.desc())
    if status:
        q = q.filter(Ticket.status == status)
    if category:
        q = q.filter(Ticket.category == category)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter((Ticket.title.like(like)) | (Ticket.ticket_no.like(like)))
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    customers = {c.id: c.name for c in db.query(Customer).all()}
    return {"total": total,
            "items": [_row(t, customers.get(t.customer_id)) for t in rows]}


@router.post("")
def create(req: CreateTicket, db: Session = Depends(get_db)):
    if not db.query(Customer).get(req.customer_id):
        raise HTTPException(404, "客户不存在")
    t = ticket_service.create_ticket(
        db, customer_id=req.customer_id, title=req.title,
        description=req.description, category=req.category,
        priority=req.priority, operator="客服")
    db.commit()
    return _row(t)


@router.get("/{ticket_no}")
def detail(ticket_no: str, db: Session = Depends(get_db)):
    t = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    if not t:
        raise HTTPException(404, "工单不存在")
    events = db.query(TicketEvent).filter(TicketEvent.ticket_id == t.id) \
        .order_by(TicketEvent.created_at).all()
    customer = db.query(Customer).get(t.customer_id)
    data = _row(t, customer.name if customer else None)
    data["events"] = [{"time": e.created_at.strftime("%m-%d %H:%M"),
                       "from": e.from_status, "to": e.to_status,
                       "note": e.note, "operator": e.operator} for e in events]
    return data


@router.patch("/{ticket_no}")
def patch(ticket_no: str, req: PatchTicket, db: Session = Depends(get_db)):
    t = db.query(Ticket).filter(Ticket.ticket_no == ticket_no).first()
    if not t:
        raise HTTPException(404, "工单不存在")
    if req.assignee is not None:
        t.assignee = req.assignee
    if req.priority is not None:
        t.priority = req.priority
    try:
        if req.status and req.status != t.status:
            ticket_service.transition(db, t, req.status, note=req.note or "", operator="客服")
        elif req.note:
            ticket_service.add_note(db, t, req.note, operator="客服")
        db.commit()
    except ticket_service.InvalidTransition as e:
        db.rollback()
        raise HTTPException(409, str(e))
    return _row(t)
