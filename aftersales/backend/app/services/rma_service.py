"""退换货（RMA）状态机、政策计算与业务操作"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import Order, RmaEvent, RmaRequest

TRANSITIONS: dict[str, list[str]] = {
    "已提交": ["已批准", "已驳回", "已取消"],
    "已批准": ["待寄回"],
    "待寄回": ["已收货", "已取消"],
    "已收货": ["处理中"],
    "处理中": ["已完成"],
    "已完成": [],
    "已驳回": [],
    "已取消": [],
}


class InvalidTransition(Exception):
    pass


def gen_rma_no(db: Session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"RMA{today}-"
    last = db.query(RmaRequest.rma_no).filter(RmaRequest.rma_no.like(f"{prefix}%")) \
        .order_by(RmaRequest.rma_no.desc()).first()
    seq = int(last[0].rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{seq:04d}"


def check_policy(order: Order, request_type: str) -> dict:
    """按签收日期计算 退货/换货/维修 资格。返回 {eligible, reason, deadline}"""
    p = order.product
    if order.delivered_at is None:
        return {"eligible": False,
                "reason": f"订单 {order.order_no} 尚未签收（当前状态：{order.status}），签收后才能办理售后。如需取消订单请联系人工客服。",
                "deadline": None}
    now = datetime.now()
    days_since = (now - order.delivered_at).days
    if request_type == "退货":
        deadline = order.delivered_at + timedelta(days=p.return_days)
        ok = now <= deadline
        return {"eligible": ok, "deadline": deadline.strftime("%Y-%m-%d"),
                "reason": (f"签收已 {days_since} 天，在 {p.return_days} 天无理由退货期内，可退货" if ok
                           else f"签收已 {days_since} 天，已超过 {p.return_days} 天无理由退货期（截止 {deadline:%Y-%m-%d}），无法退货")}
    if request_type == "换货":
        deadline = order.delivered_at + timedelta(days=p.exchange_days)
        ok = now <= deadline
        return {"eligible": ok, "deadline": deadline.strftime("%Y-%m-%d"),
                "reason": (f"签收已 {days_since} 天，在 {p.exchange_days} 天换货期内，可换货" if ok
                           else f"签收已 {days_since} 天，已超过 {p.exchange_days} 天换货期（截止 {deadline:%Y-%m-%d}），无法换货")}
    # 维修：保修期
    deadline = order.delivered_at + timedelta(days=p.warranty_months * 30)
    ok = now <= deadline
    return {"eligible": ok, "deadline": deadline.strftime("%Y-%m-%d"),
            "reason": (f"产品在 {p.warranty_months} 个月保修期内（截止 {deadline:%Y-%m-%d}），可免费维修" if ok
                       else f"产品已超过 {p.warranty_months} 个月保修期（截止 {deadline:%Y-%m-%d}），只能付费维修")}


def create_rma(db: Session, *, order: Order, customer_id: int, rma_type: str,
               reason: str, conversation_id: int | None = None,
               operator: str = "AI助手") -> RmaRequest:
    rma = RmaRequest(
        rma_no=gen_rma_no(db), order_id=order.id, customer_id=customer_id,
        conversation_id=conversation_id, type=rma_type, reason=reason,
        status="已提交",
        refund_amount=order.amount if rma_type == "退货" else None,
    )
    db.add(rma)
    db.flush()
    db.add(RmaEvent(rma_id=rma.id, from_status=None, to_status="已提交",
                    note=f"{rma_type}申请提交：{reason}", operator=operator))
    return rma


def transition(db: Session, rma: RmaRequest, to_status: str,
               note: str = "", operator: str = "客服") -> RmaRequest:
    allowed = TRANSITIONS.get(rma.status, [])
    if to_status not in allowed:
        raise InvalidTransition(
            f"退换货单 {rma.rma_no} 不能从「{rma.status}」变为「{to_status}」，"
            f"允许的下一状态：{allowed or '（终态）'}")
    from_status = rma.status
    rma.status = to_status
    rma.updated_at = datetime.now()
    db.add(RmaEvent(rma_id=rma.id, from_status=from_status, to_status=to_status,
                    note=note, operator=operator))
    # 主动服务：状态变化即时推送客户通知
    from . import reminder_service
    reminder_service.notify_rma_update(db, rma, note=note)
    return rma
