"""自我学习路由：触发分析、审核候选"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AnalysisRun, Conversation, LearningCandidate
from ..services import learning_service

router = APIRouter(prefix="/api/learning", tags=["learning"])


@router.post("/analyze")
def analyze(background: BackgroundTasks, db: Session = Depends(get_db)):
    running = db.query(AnalysisRun).filter(AnalysisRun.status == "running").first()
    if running:
        raise HTTPException(409, f"已有分析任务在运行（批次 #{running.id}）")
    pending = db.query(Conversation).filter(
        Conversation.status == "closed",
        Conversation.analyzed == False).count()  # noqa: E712
    run = AnalysisRun(trigger="manual")
    db.add(run)
    db.commit()
    background.add_task(learning_service.run_analysis, run.id)
    return {"ok": True, "run_id": run.id, "pending_conversations": pending}


@router.get("/runs")
def runs(db: Session = Depends(get_db)):
    rows = db.query(AnalysisRun).order_by(AnalysisRun.id.desc()).limit(10).all()
    return {"items": [{
        "id": r.id, "status": r.status, "trigger": r.trigger,
        "scanned": r.conversations_scanned, "created": r.candidates_created,
        "started_at": r.started_at.strftime("%m-%d %H:%M"),
        "finished_at": r.finished_at.strftime("%m-%d %H:%M") if r.finished_at else None,
        "error": r.error} for r in rows]}


def _cand_row(c: LearningCandidate) -> dict:
    return {
        "id": c.id, "type": c.type, "question": c.question,
        "suggested_answer": c.suggested_answer, "category": c.category,
        "frequency": c.frequency, "confidence": c.confidence,
        "status": c.status, "review_note": c.review_note,
        "source_conversation_id": c.source_conversation_id,
        "kb_entry_id": c.kb_entry_id,
        "created_at": c.created_at.strftime("%Y-%m-%d %H:%M"),
    }


@router.get("/candidates")
def candidates(status: str = "pending", type: str | None = None,
               db: Session = Depends(get_db)):
    q = db.query(LearningCandidate).filter(LearningCandidate.status == status)
    if type:
        q = q.filter(LearningCandidate.type == type)
    # 热点置顶，其次按频次与时间
    rows = q.all()
    rows.sort(key=lambda c: (c.type != "hot_issue", -c.frequency, -c.id))
    return {"items": [_cand_row(c) for c in rows]}


class ApprovePayload(BaseModel):
    question: str | None = None
    answer: str | None = None
    category: str | None = None


class RejectPayload(BaseModel):
    review_note: str = ""


@router.post("/candidates/{cand_id}/approve")
def approve(cand_id: int, req: ApprovePayload, db: Session = Depends(get_db)):
    c = db.query(LearningCandidate).get(cand_id)
    if not c:
        raise HTTPException(404, "候选不存在")
    if c.status != "pending":
        raise HTTPException(409, f"候选已{('通过' if c.status == 'approved' else '驳回')}")
    try:
        entry = learning_service.approve_candidate(
            db, c, question=req.question, answer=req.answer, category=req.category)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "kb_entry_id": entry.id, "candidate": _cand_row(c)}


@router.post("/candidates/{cand_id}/reject")
def reject(cand_id: int, req: RejectPayload, db: Session = Depends(get_db)):
    c = db.query(LearningCandidate).get(cand_id)
    if not c:
        raise HTTPException(404, "候选不存在")
    if c.status != "pending":
        raise HTTPException(409, "候选已处理")
    learning_service.reject_candidate(db, c, note=req.review_note)
    return {"ok": True, "candidate": _cand_row(c)}
