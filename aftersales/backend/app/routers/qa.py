"""AI 会话质检路由：LLM 对会话服务质量打分（结果存入会话摘要）"""
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..llm.anthropic_client import get_llm_client
from ..models import Conversation
from ..services import learning_service
from ..services.auth_service import get_current_staff

router = APIRouter(prefix="/api/qa", tags=["qa"])


def _load_payload(conv: Conversation) -> dict:
    try:
        payload = json.loads(conv.summary or "{}")
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        return {}


@router.post("/conversations/{conv_id}")
def review(conv_id: int, db: Session = Depends(get_db),
           _staff=Depends(get_current_staff)):
    conv = db.query(Conversation).get(conv_id)
    if not conv:
        raise HTTPException(404, "会话不存在")
    transcript = learning_service.build_transcript(db, conv)
    if len(transcript) < 10:
        raise HTTPException(400, "会话内容太少，无法质检")
    llm = get_llm_client()
    try:
        result = llm.qa_review(transcript)
    except Exception as e:
        raise HTTPException(502, f"质检失败：{e}")
    payload = _load_payload(conv)
    payload["qa"] = {
        "score": int(result.get("score", 0)),
        "dimensions": result.get("dimensions", {}),
        "issues": result.get("issues", []),
        "suggestion": result.get("suggestion", ""),
    }
    conv.summary = json.dumps(payload, ensure_ascii=False)
    db.commit()
    return {"ok": True, "qa": payload["qa"]}


@router.get("/conversations/{conv_id}")
def get_review(conv_id: int, db: Session = Depends(get_db),
               _staff=Depends(get_current_staff)):
    conv = db.query(Conversation).get(conv_id)
    if not conv:
        raise HTTPException(404, "会话不存在")
    return {"qa": _load_payload(conv).get("qa")}
