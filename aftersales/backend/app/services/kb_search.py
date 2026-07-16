"""知识库中文检索：jieba 分词 + FTS5 bm25 + LIKE 兜底

FTS5 unicode61 分词器把连续汉字当成一个 token，中文必须先分词。
写入与查询两侧统一走 segment()，索引同步在 Python 层完成。
"""
import re

import jieba
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models import KbEntry
from . import embedding_service

_WORD_RE = re.compile(r"[\w一-鿿]+")


def segment(s: str) -> str:
    """jieba 分词并用空格连接（只保留中英文数字 token）"""
    if not s:
        return ""
    tokens = []
    for tok in jieba.cut_for_search(s):
        tok = tok.strip()
        if tok and _WORD_RE.fullmatch(tok):
            tokens.append(tok)
    return " ".join(tokens)


def upsert_index(db: Session, entry: KbEntry, embed: bool = True):
    db.execute(text("DELETE FROM kb_fts WHERE entry_id = :eid"), {"eid": entry.id})
    if entry.status == "published":
        db.execute(
            text("INSERT INTO kb_fts (entry_id, title_seg, question_seg, answer_seg) "
                 "VALUES (:eid, :t, :q, :a)"),
            {"eid": entry.id, "t": segment(entry.title),
             "q": segment(entry.question), "a": segment(entry.answer)},
        )
        if embed:
            vec = embedding_service.embed_one(
                f"{entry.title}\n{entry.question}\n{entry.answer[:800]}")
            if vec:
                entry.embedding = embedding_service.to_json(vec)


def delete_index(db: Session, entry_id: int):
    db.execute(text("DELETE FROM kb_fts WHERE entry_id = :eid"), {"eid": entry_id})


def reindex_all(db: Session) -> int:
    db.execute(text("DELETE FROM kb_fts"))
    entries = db.query(KbEntry).filter(KbEntry.status == "published").all()
    # 批量补齐缺失的向量（一次 API 调用）
    missing = [e for e in entries if not e.embedding]
    if missing:
        vecs = embedding_service.embed_texts(
            [f"{e.title}\n{e.question}\n{e.answer[:800]}" for e in missing])
        if vecs:
            for e, v in zip(missing, vecs):
                e.embedding = embedding_service.to_json(v)
    for e in entries:
        upsert_index(db, e, embed=False)
    db.commit()
    return len(entries)


def _fts_ranked_ids(db: Session, query: str, limit: int = 20) -> tuple[list[int], dict]:
    seg = segment(query)
    if not seg:
        return [], {}
    tokens = seg.split()
    strong = [t for t in tokens if len(t) >= 2]
    match_expr = " OR ".join(f'"{t}"' for t in (strong or tokens))
    try:
        rows = db.execute(
            text("SELECT entry_id, bm25(kb_fts, 5.0, 3.0, 1.0) AS score "
                 "FROM kb_fts WHERE kb_fts MATCH :m ORDER BY score LIMIT :k"),
            {"m": match_expr, "k": limit}).fetchall()
    except Exception:
        return [], {}
    return [r[0] for r in rows], {r[0]: -float(r[1]) for r in rows}


def search(db: Session, query: str, category: str | None = None,
           top_k: int = 3, count_hit: bool = False) -> list[dict]:
    """混合检索：FTS(bm25) + 向量语义（RRF融合）；全部落空时 LIKE 兜底"""
    results: list[dict] = []
    fts_ids, fts_scores = _fts_ranked_ids(db, query)

    vec_ids, vec_sims = [], {}
    qvec = embedding_service.embed_one(query)
    if qvec:
        cands = db.query(KbEntry.id, KbEntry.embedding) \
            .filter(KbEntry.status == "published",
                    KbEntry.embedding.isnot(None)).all()
        ranked = embedding_service.vector_rank(qvec, cands, top_k=10)
        vec_ids = [cid for cid, _ in ranked]
        vec_sims = dict(ranked)

    merged = embedding_service.rrf_merge([fts_ids, vec_ids], top_k=top_k * 3) \
        if vec_ids else fts_ids
    if merged:
        q = db.query(KbEntry).filter(KbEntry.id.in_(merged), KbEntry.status == "published")
        if category:
            q = q.filter(KbEntry.category == category)
        entries = {e.id: e for e in q.all()}
        for eid in merged:
            if eid in entries:
                score = fts_scores.get(eid) or round(vec_sims.get(eid, 0) * 10, 3)
                results.append(_row(entries[eid], round(score, 3)))
            if len(results) >= top_k:
                break

    if not results:
        # LIKE 兜底：用 jieba 关键词逐个模糊匹配
        keywords = [t for t in segment(query).split() if len(t) >= 2] or [query.strip()]
        q = db.query(KbEntry).filter(KbEntry.status == "published")
        if category:
            q = q.filter(KbEntry.category == category)
        seen = set()
        for kw in keywords[:5]:
            like = f"%{kw}%"
            for e in q.filter((KbEntry.title.like(like)) | (KbEntry.question.like(like))).limit(top_k).all():
                if e.id not in seen:
                    seen.add(e.id)
                    results.append(_row(e, 0.0))
            if len(results) >= top_k:
                break
        results = results[:top_k]

    if count_hit and results:
        for r in results:
            db.query(KbEntry).filter(KbEntry.id == r["id"]).update(
                {KbEntry.hit_count: KbEntry.hit_count + 1})
    return results


def _row(e: KbEntry, score: float) -> dict:
    return {"id": e.id, "title": e.title, "question": e.question,
            "answer": e.answer, "category": e.category, "score": score}
