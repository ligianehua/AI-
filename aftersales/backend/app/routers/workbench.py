"""人工客服工作台：转人工队列、接管/交还/结束、客服回复、AI 推荐话术"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..llm.anthropic_client import get_llm_client
from ..models import Conversation, Customer, Message, Staff
from ..services.auth_service import get_current_staff

router = APIRouter(prefix="/api/workbench", tags=["workbench"])


def _conv_brief(db: Session, c: Conversation) -> dict:
    customer = db.query(Customer).get(c.customer_id)
    last = db.query(Message).filter(Message.conversation_id == c.id,
                                    Message.role != "notice") \
        .order_by(Message.id.desc()).first()
    return {"id": c.id, "title": c.title, "mode": c.mode,
            "assigned_agent": c.assigned_agent, "handed_off": c.handed_off,
            "customer_name": customer.name if customer else "?",
            "customer_level": customer.level if customer else "",
            "last_text": (last.display_text[:40] if last else ""),
            "last_at": (last.created_at.strftime("%H:%M") if last else ""),
            "created_at": c.created_at.strftime("%m-%d %H:%M")}


@router.get("/queue")
def queue(db: Session = Depends(get_db), staff: Staff = Depends(get_current_staff)):
    """待接入 = 已转人工但无人接管；服务中 = 人工模式"""
    active = db.query(Conversation).filter(Conversation.status == "active")
    waiting = active.filter(Conversation.handed_off == True,  # noqa: E712
                            Conversation.mode == "ai") \
        .order_by(Conversation.created_at.desc()).all()
    serving = active.filter(Conversation.mode == "human") \
        .order_by(Conversation.created_at.desc()).all()
    return {"waiting": [_conv_brief(db, c) for c in waiting],
            "serving": [_conv_brief(db, c) for c in serving],
            "me": staff.display_name}


def _notice(db: Session, conv: Conversation, text: str):
    db.add(Message(conversation_id=conv.id, role="notice", display_text=text))


@router.post("/conversations/{conv_id}/takeover")
def takeover(conv_id: int, db: Session = Depends(get_db),
             staff: Staff = Depends(get_current_staff)):
    conv = db.query(Conversation).get(conv_id)
    if not conv or conv.status != "active":
        raise HTTPException(404, "会话不存在或已结束")
    if conv.mode == "human" and conv.assigned_agent != staff.display_name:
        raise HTTPException(409, f"该会话已由 {conv.assigned_agent} 接管")
    conv.mode = "human"
    conv.assigned_agent = staff.display_name
    conv.handed_off = True
    _notice(db, conv, f"人工客服 {staff.display_name} 已接入，为您继续服务")
    db.commit()
    return {"ok": True, "mode": conv.mode, "assigned_agent": conv.assigned_agent}


@router.post("/conversations/{conv_id}/release")
def release(conv_id: int, db: Session = Depends(get_db),
            staff: Staff = Depends(get_current_staff)):
    conv = db.query(Conversation).get(conv_id)
    if not conv or conv.mode != "human":
        raise HTTPException(404, "会话不在人工服务中")
    conv.mode = "ai"
    conv.assigned_agent = None
    _notice(db, conv, f"人工客服 {staff.display_name} 已退出，AI 助手将继续为您服务")
    db.commit()
    return {"ok": True, "mode": conv.mode}


class ReplyPayload(BaseModel):
    text: str


@router.post("/conversations/{conv_id}/reply")
def reply(conv_id: int, req: ReplyPayload, db: Session = Depends(get_db),
          staff: Staff = Depends(get_current_staff)):
    conv = db.query(Conversation).get(conv_id)
    if not conv or conv.status != "active":
        raise HTTPException(404, "会话不存在或已结束")
    if conv.mode != "human":
        raise HTTPException(409, "请先接管会话再回复")
    text = req.text.strip()
    if not text:
        raise HTTPException(400, "回复不能为空")
    msg = Message(conversation_id=conv.id, role="assistant",
                  agent_name=staff.display_name, display_text=text)
    db.add(msg)
    db.commit()
    return {"ok": True, "message_id": msg.id}


@router.post("/conversations/{conv_id}/finish")
def finish(conv_id: int, db: Session = Depends(get_db),
           staff: Staff = Depends(get_current_staff)):
    conv = db.query(Conversation).get(conv_id)
    if not conv:
        raise HTTPException(404, "会话不存在")
    conv.status = "closed"
    conv.mode = "ai"
    conv.closed_at = datetime.now()
    _notice(db, conv, f"客服 {staff.display_name} 已结束本次会话，感谢您的咨询")
    db.commit()
    return {"ok": True}


@router.post("/conversations/{conv_id}/suggest")
def suggest(conv_id: int, db: Session = Depends(get_db),
            staff: Staff = Depends(get_current_staff)):
    """AI 推荐话术：给客服生成一条可编辑的回复建议"""
    conv = db.query(Conversation).get(conv_id)
    if not conv:
        raise HTTPException(404, "会话不存在")
    rows = db.query(Message).filter(Message.conversation_id == conv.id,
                                    Message.role != "notice") \
        .order_by(Message.id.desc()).limit(12).all()
    lines = []
    for m in reversed(rows):
        who = "客户" if m.role == "user" else (m.agent_name or "AI客服")
        if m.display_text.strip():
            lines.append(f"{who}: {m.display_text.strip()[:300]}")
    transcript = "\n".join(lines)
    llm = get_llm_client()
    try:
        text = llm.suggest_reply(transcript)
    except Exception as e:
        raise HTTPException(502, f"生成建议失败：{e}")
    return {"ok": True, "suggestion": text}
