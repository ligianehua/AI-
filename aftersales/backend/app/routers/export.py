"""数据导出（CSV，带 BOM 可直接用 Excel 打开）"""
import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conversation, Customer, RmaRequest, SatisfactionRating, Ticket
from ..services.auth_service import get_current_staff

router = APIRouter(prefix="/api/export", tags=["export"])


def _csv_response(headers: list[str], rows: list[list], filename: str) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    data = "﻿" + buf.getvalue()  # BOM：Excel 正确识别 UTF-8
    stamp = datetime.now().strftime("%Y%m%d%H%M")
    return Response(
        content=data.encode("utf-8"), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f"attachment; filename={filename}_{stamp}.csv"})


@router.get("/tickets")
def export_tickets(db: Session = Depends(get_db), _staff=Depends(get_current_staff)):
    names = {c.id: c.name for c in db.query(Customer).all()}
    rows = [[t.ticket_no, t.title, t.category, t.priority, t.status,
             names.get(t.customer_id, ""), t.assignee or "",
             t.created_at.strftime("%Y-%m-%d %H:%M"),
             t.resolved_at.strftime("%Y-%m-%d %H:%M") if t.resolved_at else ""]
            for t in db.query(Ticket).order_by(Ticket.created_at.desc()).all()]
    return _csv_response(["工单号", "标题", "分类", "优先级", "状态", "客户", "处理人", "创建时间", "解决时间"],
                         rows, "tickets")


@router.get("/rma")
def export_rma(db: Session = Depends(get_db), _staff=Depends(get_current_staff)):
    rows = [[r.rma_no, r.type, r.status,
             r.order.product.name if r.order else "",
             r.customer.name if r.customer else "",
             r.reason, r.refund_amount or "",
             r.created_at.strftime("%Y-%m-%d %H:%M")]
            for r in db.query(RmaRequest).order_by(RmaRequest.created_at.desc()).all()]
    return _csv_response(["单号", "类型", "状态", "商品", "客户", "原因", "退款金额", "申请时间"],
                         rows, "rma")


@router.get("/conversations")
def export_conversations(db: Session = Depends(get_db), _staff=Depends(get_current_staff)):
    names = {c.id: c.name for c in db.query(Customer).all()}
    ratings = {r.conversation_id: r.score for r in db.query(SatisfactionRating).all()}
    rows = []
    for c in db.query(Conversation).order_by(Conversation.created_at.desc()).all():
        qa_score = ""
        try:
            payload = json.loads(c.summary or "{}")
            qa_score = (payload.get("qa") or {}).get("score", "")
        except json.JSONDecodeError:
            pass
        rows.append([c.id, c.title, names.get(c.customer_id, ""),
                     "已结束" if c.status == "closed" else "进行中",
                     "是" if c.handed_off else "否",
                     {True: "已解决", False: "未解决"}.get(c.resolved, ""),
                     ratings.get(c.id, ""), qa_score,
                     c.created_at.strftime("%Y-%m-%d %H:%M")])
    return _csv_response(["ID", "标题", "客户", "状态", "转人工", "解决结果", "满意度", "质检分", "时间"],
                         rows, "conversations")
