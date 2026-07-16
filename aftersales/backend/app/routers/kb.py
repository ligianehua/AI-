"""知识库路由"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import KbEntry
from ..services import kb_search, manual_service

router = APIRouter(prefix="/api/kb", tags=["kb"])


def _row(e: KbEntry, score: float | None = None) -> dict:
    d = {
        "id": e.id, "title": e.title, "question": e.question, "answer": e.answer,
        "category": e.category, "tags": e.tags, "entry_type": e.entry_type,
        "source": e.source, "status": e.status, "hit_count": e.hit_count,
        "updated_at": e.updated_at.strftime("%Y-%m-%d %H:%M"),
    }
    if score is not None:
        d["score"] = score
    return d


class KbPayload(BaseModel):
    title: str
    question: str = ""
    answer: str
    category: str = "其他"
    tags: str = ""
    entry_type: str = "faq"
    status: str = "published"


@router.get("")
def list_kb(q: str | None = None, category: str | None = None,
            status: str | None = None, source: str | None = None,
            page: int = 1, size: int = 100, db: Session = Depends(get_db)):
    if q:
        hits = kb_search.search(db, q, category=category, top_k=20)
        db.commit()
        return {"total": len(hits), "search": True,
                "items": [dict(h, source=_src(db, h["id"])) for h in hits]}
    query = db.query(KbEntry).order_by(KbEntry.updated_at.desc())
    if category:
        query = query.filter(KbEntry.category == category)
    if status:
        query = query.filter(KbEntry.status == status)
    if source:
        query = query.filter(KbEntry.source == source)
    total = query.count()
    rows = query.offset((page - 1) * size).limit(size).all()
    return {"total": total, "search": False, "items": [_row(e) for e in rows]}


def _src(db: Session, entry_id: int) -> str:
    e = db.query(KbEntry).get(entry_id)
    return e.source if e else "manual"


@router.post("")
def create(req: KbPayload, db: Session = Depends(get_db)):
    e = KbEntry(**req.model_dump(), source="manual")
    db.add(e)
    db.flush()
    kb_search.upsert_index(db, e)
    db.commit()
    return _row(e)


@router.put("/{entry_id}")
def update(entry_id: int, req: KbPayload, db: Session = Depends(get_db)):
    e = db.query(KbEntry).get(entry_id)
    if not e:
        raise HTTPException(404, "条目不存在")
    for k, v in req.model_dump().items():
        setattr(e, k, v)
    kb_search.upsert_index(db, e)
    db.commit()
    return _row(e)


@router.delete("/{entry_id}")
def delete(entry_id: int, db: Session = Depends(get_db)):
    e = db.query(KbEntry).get(entry_id)
    if not e:
        raise HTTPException(404, "条目不存在")
    kb_search.delete_index(db, entry_id)
    db.delete(e)
    db.commit()
    return {"ok": True}


@router.post("/reindex")
def reindex(db: Session = Depends(get_db)):
    n = kb_search.reindex_all(db)
    m = manual_service.backfill_embeddings(db)
    return {"ok": True, "indexed": n, "manual_chunks_embedded": m}
