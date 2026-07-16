"""提醒/通知路由：客户看自己的通知；员工看提醒中心并可手动扫描"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, Reminder
from ..services import reminder_service
from ..services.auth_service import get_current_customer, get_current_staff

router = APIRouter(tags=["reminders"])

TYPE_NAMES = {"warranty_expiry": "保修到期", "maintenance": "保养提醒",
              "rma_update": "售后进度", "low_rating_followup": "差评回访",
              "hot_issue_alert": "热点预警"}


def _row(r: Reminder, customer_name: str | None = None) -> dict:
    return {"id": r.id, "type": r.type, "type_name": TYPE_NAMES.get(r.type, r.type),
            "title": r.title, "content": r.content, "related_no": r.related_no,
            "audience": r.audience, "status": r.status,
            "customer_id": r.customer_id, "customer_name": customer_name,
            "created_at": r.created_at.strftime("%m-%d %H:%M")}


# ---------- 客户侧通知 ----------

@router.get("/api/notifications")
def my_notifications(db: Session = Depends(get_db),
                     customer: Customer = Depends(get_current_customer)):
    rows = db.query(Reminder).filter(Reminder.customer_id == customer.id,
                                     Reminder.audience == "customer") \
        .order_by(Reminder.created_at.desc()).limit(20).all()
    unread = sum(1 for r in rows if r.status == "pending")
    return {"unread": unread, "items": [_row(r) for r in rows]}


@router.post("/api/notifications/{rid}/read")
def mark_read(rid: int, db: Session = Depends(get_db),
              customer: Customer = Depends(get_current_customer)):
    r = db.query(Reminder).get(rid)
    if not r or r.customer_id != customer.id:
        raise HTTPException(404, "通知不存在")
    r.status = "done"
    db.commit()
    return {"ok": True}


# ---------- 员工侧提醒中心 ----------

@router.get("/api/reminders")
def list_reminders(status: str | None = None, type: str | None = None,
                   db: Session = Depends(get_db), _staff=Depends(get_current_staff)):
    q = db.query(Reminder).order_by(Reminder.created_at.desc())
    if status:
        q = q.filter(Reminder.status == status)
    if type:
        q = q.filter(Reminder.type == type)
    rows = q.limit(200).all()
    names = {c.id: c.name for c in db.query(Customer).all()}
    return {"items": [_row(r, names.get(r.customer_id)) for r in rows]}


@router.post("/api/reminders/scan")
def manual_scan(db: Session = Depends(get_db), _staff=Depends(get_current_staff)):
    created = reminder_service.scan(db)
    total = sum(created.values())
    return {"ok": True, "created": created,
            "message": f"扫描完成：新增 {total} 条提醒"
                       f"（保修{created['warranty']} / 保养{created['maintenance']} / 回访{created['followup']}）"}


@router.post("/api/reminders/{rid}/done")
def mark_done(rid: int, db: Session = Depends(get_db), _staff=Depends(get_current_staff)):
    r = db.query(Reminder).get(rid)
    if not r:
        raise HTTPException(404, "提醒不存在")
    r.status = "done"
    db.commit()
    return {"ok": True}
