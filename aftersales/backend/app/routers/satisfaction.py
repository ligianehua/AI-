"""满意度路由"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conversation, Customer, SatisfactionRating
from ..services.auth_service import get_current_customer, get_current_staff

router = APIRouter(prefix="/api/satisfaction", tags=["satisfaction"])


class RatePayload(BaseModel):
    conversation_id: int
    score: int
    comment: str = ""


@router.post("")
def rate(req: RatePayload, db: Session = Depends(get_db),
         customer: Customer = Depends(get_current_customer)):
    conv = db.query(Conversation).get(req.conversation_id)
    if not conv or conv.customer_id != customer.id:
        raise HTTPException(404, "会话不存在")
    score = max(1, min(5, req.score))
    existing = db.query(SatisfactionRating).filter(
        SatisfactionRating.conversation_id == conv.id).first()
    if existing:
        existing.score = score
        existing.comment = req.comment
    else:
        db.add(SatisfactionRating(conversation_id=conv.id,
                                  customer_id=conv.customer_id,
                                  score=score, comment=req.comment))
    db.commit()
    return {"ok": True, "score": score}


@router.get("/stats")
def stats(db: Session = Depends(get_db), _staff=Depends(get_current_staff)):
    rows = db.query(SatisfactionRating).all()
    if not rows:
        return {"count": 0, "avg": None, "dist": {}}
    dist: dict[str, int] = {}
    for r in rows:
        dist[str(r.score)] = dist.get(str(r.score), 0) + 1
    return {"count": len(rows),
            "avg": round(sum(r.score for r in rows) / len(rows), 2),
            "dist": dist}
