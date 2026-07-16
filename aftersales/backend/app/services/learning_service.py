"""自我学习闭环：离线分析已关闭会话 -> 生成学习候选 -> 人工审核入库知识库"""
import json
import re
from datetime import datetime

import jieba
from sqlalchemy.orm import Session

from ..llm.anthropic_client import get_llm_client
from ..models import (
    AnalysisRun,
    Conversation,
    KbEntry,
    LearningCandidate,
    Message,
    SatisfactionRating,
)
from . import kb_search

HOT_ISSUE_THRESHOLD = 3  # 相似候选出现次数 >= 3 视为热点


def _tokens(text: str) -> set[str]:
    return {t for t in jieba.cut(text) if len(t.strip()) >= 2}


def _similar(a: str, b: str, threshold: float = 0.6) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return a.strip() == b.strip()
    jaccard = len(ta & tb) / len(ta | tb)
    return jaccard >= threshold


def build_transcript(db: Session, conv: Conversation) -> str:
    rows = db.query(Message).filter(Message.conversation_id == conv.id) \
        .order_by(Message.id).all()
    lines = []
    for m in rows:
        role = "客户" if m.role == "user" else "客服"
        text = (m.display_text or "").strip()
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


def run_analysis(run_id: int):
    """后台任务入口：分析所有未分析的已关闭会话"""
    from ..database import SessionLocal
    db = SessionLocal()
    try:
        run = db.query(AnalysisRun).get(run_id)
        llm = get_llm_client()
        convs = db.query(Conversation).filter(
            Conversation.status == "closed",
            Conversation.analyzed == False).all()  # noqa: E712
        created = 0
        for conv in convs:
            transcript = build_transcript(db, conv)
            if len(transcript) < 10:
                conv.analyzed = True
                continue
            try:
                result = llm.analyze_conversation(transcript)
            except Exception:
                continue  # 单条失败不阻塞整批

            created += _ingest_result(db, conv, result)
            conv.analyzed = True
            conv.resolved = result.resolved
            _merge_summary(conv, result.summary, result.issue_tags)
            db.commit()

        run.conversations_scanned = len(convs)
        run.candidates_created = created
        run.status = "done"
        run.finished_at = datetime.now()
        db.commit()
    except Exception as e:
        db.rollback()
        run = db.query(AnalysisRun).get(run_id)
        if run:
            run.status = "failed"
            run.error = str(e)
            run.finished_at = datetime.now()
            db.commit()
    finally:
        db.close()


def _merge_summary(conv: Conversation, summary: str, tags: list[str]):
    try:
        payload = json.loads(conv.summary or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except json.JSONDecodeError:
        payload = {}
    payload["text"] = summary
    payload["tags"] = tags
    conv.summary = json.dumps(payload, ensure_ascii=False)


def _ingest_result(db: Session, conv: Conversation, result) -> int:
    """把分析结果转成候选（去重合并），返回新建候选数"""
    created = 0

    # 差评/转人工信号 → 补充 kb_gap
    gaps = list(result.kb_gaps)
    rating = db.query(SatisfactionRating).filter(
        SatisfactionRating.conversation_id == conv.id).first()
    if (not result.resolved or conv.handed_off or (rating and rating.score <= 2)):
        if not gaps and result.faq_candidates:
            pass  # 已有 faq 候选则不强造 gap
        elif not gaps:
            first_q = _first_user_question(db, conv)
            if first_q:
                gaps.append({"question": first_q, "context": "会话未解决/转人工/差评，需补充知识或流程"})

    for item in result.faq_candidates:
        created += _upsert_candidate(
            db, conv, ctype="faq", question=item.get("question", ""),
            answer=item.get("suggested_answer"), category=result.category,
            confidence=float(item.get("confidence", 0.5)))

    for item in gaps:
        created += _upsert_candidate(
            db, conv, ctype="kb_gap", question=item.get("question", ""),
            answer=None, category=result.category, confidence=0.5,
            note=item.get("context"))
    return created


def _first_user_question(db: Session, conv: Conversation) -> str:
    m = db.query(Message).filter(Message.conversation_id == conv.id,
                                 Message.role == "user").order_by(Message.id).first()
    return (m.display_text or "").strip()[:200] if m else ""


def _upsert_candidate(db: Session, conv: Conversation, *, ctype: str, question: str,
                      answer: str | None, category: str, confidence: float,
                      note: str | None = None) -> int:
    question = (question or "").strip()
    if len(question) < 4:
        return 0

    # 已被知识库覆盖 → 丢弃
    published = db.query(KbEntry).filter(KbEntry.status == "published").all()
    for e in published:
        if _similar(question, e.question or e.title):
            return 0

    # 与已有 pending 候选相似 → 合并计数
    pendings = db.query(LearningCandidate).filter(
        LearningCandidate.status == "pending").all()
    for c in pendings:
        if _similar(question, c.question):
            c.frequency += 1
            if answer and confidence > c.confidence:
                c.suggested_answer = answer
                c.confidence = confidence
            if c.frequency >= HOT_ISSUE_THRESHOLD and c.type != "hot_issue":
                c.type = "hot_issue"
            return 0

    db.add(LearningCandidate(
        type=ctype, question=question, suggested_answer=answer,
        category=category, source_conversation_id=conv.id,
        confidence=confidence, review_note=note))
    return 1


def add_feedback_gap(db: Session, conv: Conversation, question: str):
    """客户点踩回答 -> 该问题回流为知识缺口候选（与既有候选/知识库自动去重合并）"""
    _upsert_candidate(db, conv, ctype="kb_gap", question=question,
                      answer=None, category="其他", confidence=0.5,
                      note="客户对 AI 回答点踩，可能存在知识缺口或答案质量问题")


def approve_candidate(db: Session, candidate: LearningCandidate, *,
                      question: str | None = None, answer: str | None = None,
                      category: str | None = None, reviewer: str = "管理员") -> KbEntry:
    q = (question or candidate.question).strip()
    a = (answer or candidate.suggested_answer or "").strip()
    if not a:
        raise ValueError("入库需要答案内容，请补充答案后再通过")
    entry = KbEntry(
        title=q[:100], question=q, answer=a,
        category=category or candidate.category, entry_type="faq",
        source="learned", status="published", source_candidate_id=candidate.id)
    db.add(entry)
    db.flush()
    kb_search.upsert_index(db, entry)
    candidate.status = "approved"
    candidate.kb_entry_id = entry.id
    candidate.reviewer = reviewer
    candidate.reviewed_at = datetime.now()
    db.commit()
    return entry


def reject_candidate(db: Session, candidate: LearningCandidate, *,
                     note: str = "", reviewer: str = "管理员"):
    candidate.status = "rejected"
    candidate.review_note = note or candidate.review_note
    candidate.reviewer = reviewer
    candidate.reviewed_at = datetime.now()
    db.commit()


def hot_issue_tags(db: Session, days: int = 30) -> list[dict]:
    """从会话 summary.tags 聚合热点问题 TopN"""
    from datetime import timedelta
    since = datetime.now() - timedelta(days=days)
    prev_since = since - timedelta(days=days)
    counts: dict[str, int] = {}
    prev_counts: dict[str, int] = {}
    rows = db.query(Conversation).filter(Conversation.summary.isnot(None)).all()
    for conv in rows:
        try:
            payload = json.loads(conv.summary or "{}")
            tags = payload.get("tags") or []
        except json.JSONDecodeError:
            continue
        bucket = None
        if conv.created_at >= since:
            bucket = counts
        elif conv.created_at >= prev_since:
            bucket = prev_counts
        if bucket is None:
            continue
        for tag in tags:
            tag = re.sub(r"\s+", "", str(tag))[:30]
            if tag:
                bucket[tag] = bucket.get(tag, 0) + 1
    out = []
    for tag, n in sorted(counts.items(), key=lambda kv: -kv[1])[:10]:
        prev = prev_counts.get(tag, 0)
        out.append({"tag": tag, "count": n, "prev": prev,
                    "trend": ("up" if n > prev else "down" if n < prev else "flat")})
    return out
