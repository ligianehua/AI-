"""退换货（RMA）路由"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Order, RmaEvent, RmaRequest
from ..services import rma_service

router = APIRouter(prefix="/api/rma", tags=["rma"])


def _row(r: RmaRequest) -> dict:
    return {
        "id": r.id, "rma_no": r.rma_no, "type": r.type, "status": r.status,
        "reason": r.reason, "refund_amount": r.refund_amount,
        "order_no": r.order.order_no if r.order else None,
        "product": r.order.product.name if r.order else None,
        "customer_name": r.customer.name if r.customer else None,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
        "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M"),
        "next_statuses": rma_service.TRANSITIONS.get(r.status, []),
    }


class CreateRma(BaseModel):
    order_no: str
    type: str
    reason: str = ""


class PatchRma(BaseModel):
    status: str
    note: str = ""


@router.get("")
def list_rma(status: str | None = None, page: int = 1, size: int = 100,
             db: Session = Depends(get_db)):
    q = db.query(RmaRequest).order_by(RmaRequest.updated_at.desc())
    if status:
        q = q.filter(RmaRequest.status == status)
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    return {"total": total, "items": [_row(r) for r in rows]}


@router.post("")
def create(req: CreateRma, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.order_no == req.order_no).first()
    if not order:
        raise HTTPException(404, "订单不存在")
    policy = rma_service.check_policy(order, req.type)
    if not policy["eligible"]:
        raise HTTPException(409, f"不符合{req.type}政策：{policy['reason']}")
    r = rma_service.create_rma(db, order=order, customer_id=order.customer_id,
                               rma_type=req.type, reason=req.reason, operator="客服")
    db.commit()
    return _row(r)


@router.get("/{rma_no}")
def detail(rma_no: str, db: Session = Depends(get_db)):
    r = db.query(RmaRequest).filter(RmaRequest.rma_no == rma_no).first()
    if not r:
        raise HTTPException(404, "退换货单不存在")
    events = db.query(RmaEvent).filter(RmaEvent.rma_id == r.id) \
        .order_by(RmaEvent.created_at).all()
    data = _row(r)
    data["events"] = [{"time": e.created_at.strftime("%m-%d %H:%M"),
                       "from": e.from_status, "to": e.to_status,
                       "note": e.note, "operator": e.operator} for e in events]
    return data


@router.patch("/{rma_no}")
def patch(rma_no: str, req: PatchRma, db: Session = Depends(get_db)):
    r = db.query(RmaRequest).filter(RmaRequest.rma_no == rma_no).first()
    if not r:
        raise HTTPException(404, "退换货单不存在")
    try:
        rma_service.transition(db, r, req.status, note=req.note, operator="客服")
        db.commit()
    except rma_service.InvalidTransition as e:
        db.rollback()
        raise HTTPException(409, str(e))
    return _row(r)
