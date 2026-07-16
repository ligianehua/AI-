"""会话管理路由（客户看自己的，员工看全量）"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conversation, Customer, Message
from ..services.auth_service import get_actor, get_current_customer

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _conv_row(c: Conversation, customer_name: str | None = None) -> dict:
    summary_text, tags, qa = None, [], None
    if c.summary:
        try:
            payload = json.loads(c.summary)
            summary_text = payload.get("text")
            tags = payload.get("tags") or []
            qa = payload.get("qa")
        except json.JSONDecodeError:
            summary_text = c.summary
    return {
        "id": c.id, "customer_id": c.customer_id, "customer_name": customer_name,
        "title": c.title, "status": c.status, "mode": c.mode,
        "assigned_agent": c.assigned_agent,
        "resolved": c.resolved, "handed_off": c.handed_off, "analyzed": c.analyzed,
        "summary": summary_text, "tags": tags, "qa": qa,
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M"),
        "closed_at": c.closed_at.strftime("%Y-%m-%d %H:%M") if c.closed_at else None,
    }


def _msg_rows(db: Session, conv_id: int) -> list[dict]:
    rows = db.query(Message).filter(Message.conversation_id == conv_id) \
        .order_by(Message.id).all()
    out = []
    for m in rows:
        tool_calls = []
        if m.tool_calls:
            try:
                tool_calls = json.loads(m.tool_calls)
            except json.JSONDecodeError:
                pass
        out.append({"id": m.id, "role": m.role, "text": m.display_text,
                    "agent_name": m.agent_name, "tool_calls": tool_calls,
                    "image": f"/uploads/{m.image_path}" if m.image_path else None,
                    "feedback": m.feedback,
                    "created_at": m.created_at.strftime("%H:%M")})
    return out


@router.post("")
def create(db: Session = Depends(get_db),
           customer: Customer = Depends(get_current_customer)):
    conv = Conversation(customer_id=customer.id)
    db.add(conv)
    db.commit()
    return _conv_row(conv, customer.name)


@router.get("")
def list_conversations(page: int = 1, size: int = 50,
                       actor=Depends(get_actor), db: Session = Depends(get_db)):
    kind, who = actor
    q = db.query(Conversation).order_by(Conversation.created_at.desc())
    if kind == "customer":
        q = q.filter(Conversation.customer_id == who.id)
    total = q.count()
    rows = q.offset((page - 1) * size).limit(size).all()
    customers = {c.id: c.name for c in db.query(Customer).all()}
    return {"total": total,
            "items": [_conv_row(c, customers.get(c.customer_id)) for c in rows]}


@router.get("/{conv_id}/messages")
def messages(conv_id: int, after_id: int = 0,
             actor=Depends(get_actor), db: Session = Depends(get_db)):
    kind, who = actor
    conv = db.query(Conversation).get(conv_id)
    if not conv:
        raise HTTPException(404, "会话不存在")
    if kind == "customer" and conv.customer_id != who.id:
        raise HTTPException(404, "会话不存在")
    rows = _msg_rows(db, conv_id)
    if after_id:
        rows = [m for m in rows if m["id"] > after_id]
    return {"conversation": _conv_row(conv), "messages": rows}


class FeedbackPayload(BaseModel):
    value: str  # up/down


@router.post("/{conv_id}/messages/{msg_id}/feedback")
def message_feedback(conv_id: int, msg_id: int, req: FeedbackPayload,
                     db: Session = Depends(get_db),
                     customer: Customer = Depends(get_current_customer)):
    """客户对 AI 回答点赞/点踩；点踩自动回流为知识缺口候选（自我学习闭环）"""
    conv = db.query(Conversation).get(conv_id)
    if not conv or conv.customer_id != customer.id:
        raise HTTPException(404, "会话不存在")
    msg = db.query(Message).get(msg_id)
    if not msg or msg.conversation_id != conv_id or msg.role != "assistant":
        raise HTTPException(404, "消息不存在")
    if req.value not in ("up", "down"):
        raise HTTPException(400, "value 必须是 up 或 down")
    msg.feedback = req.value
    if req.value == "down":
        # 找到该回答对应的客户问题，回流为知识缺口
        prev_user = db.query(Message).filter(
            Message.conversation_id == conv_id, Message.role == "user",
            Message.id < msg.id).order_by(Message.id.desc()).first()
        if prev_user and len((prev_user.display_text or "").strip()) >= 4:
            from ..services import learning_service
            learning_service.add_feedback_gap(db, conv, prev_user.display_text.strip())
    db.commit()
    return {"ok": True, "feedback": msg.feedback}


@router.post("/{conv_id}/close")
def close(conv_id: int, actor=Depends(get_actor), db: Session = Depends(get_db)):
    kind, who = actor
    conv = db.query(Conversation).get(conv_id)
    if not conv:
        raise HTTPException(404, "会话不存在")
    if kind == "customer" and conv.customer_id != who.id:
        raise HTTPException(404, "会话不存在")
    if conv.status != "closed":
        conv.status = "closed"
        conv.mode = "ai"
        conv.closed_at = datetime.now()
        db.commit()
    return {"ok": True, "id": conv.id, "status": conv.status}
