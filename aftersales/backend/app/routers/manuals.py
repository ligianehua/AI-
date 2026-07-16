"""产品手册路由：上传/列表/删除/检索测试/LLM消化"""
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ManualChunk, ManualDoc
from ..services import manual_service

router = APIRouter(prefix="/api/manuals", tags=["manuals"])

MAX_SIZE = 20 * 1024 * 1024  # 20MB


def _row(d: ManualDoc) -> dict:
    return {"id": d.id, "filename": d.filename, "title": d.title,
            "file_type": d.file_type, "status": d.status,
            "chunk_count": d.chunk_count, "char_count": d.char_count,
            "created_at": d.created_at.strftime("%Y-%m-%d %H:%M")}


@router.get("")
def list_manuals(db: Session = Depends(get_db)):
    rows = db.query(ManualDoc).order_by(ManualDoc.created_at.desc()).all()
    return {"items": [_row(d) for d in rows]}


@router.post("")
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(413, "文件超过 20MB 限制")
    if not data:
        raise HTTPException(400, "文件为空")
    try:
        doc = manual_service.ingest(db, file.filename or "手册.txt", data)
    except manual_service.ManualParseError as e:
        raise HTTPException(400, str(e))
    return _row(doc)


@router.get("/{doc_id}/chunks")
def chunks(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(ManualDoc).get(doc_id)
    if not doc:
        raise HTTPException(404, "手册不存在")
    rows = db.query(ManualChunk).filter(ManualChunk.doc_id == doc_id) \
        .order_by(ManualChunk.seq).all()
    return {"doc": _row(doc),
            "chunks": [{"seq": c.seq, "section": c.section,
                        "content": c.content} for c in rows]}


@router.delete("/{doc_id}")
def delete(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(ManualDoc).get(doc_id)
    if not doc:
        raise HTTPException(404, "手册不存在")
    manual_service.delete_doc(db, doc)
    return {"ok": True}


@router.get("/search")
def search(q: str, top_k: int = 5, db: Session = Depends(get_db)):
    return {"items": manual_service.search(db, q, top_k=top_k)}


@router.post("/{doc_id}/digest")
def digest(doc_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    doc = db.query(ManualDoc).get(doc_id)
    if not doc:
        raise HTTPException(404, "手册不存在")
    background.add_task(manual_service.digest_to_candidates, doc_id)
    return {"ok": True, "message": f"已开始消化《{doc.title}》，稍后在学习审核队列查看 FAQ 候选"}
