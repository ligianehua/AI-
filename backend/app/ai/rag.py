"""混合检索：向量（pgvector cosine）+ 关键词（词命中计分）→ RRF 融合。

- 关键词路：查询切词后按 ILIKE 命中数计分（locale 无关，中文可用；pg_trgm GIN 索引
  为 %词% 匹配加速）。BM25 需中文分词扩展，不在 pgvector 镜像内，接口不变可后换
- 嵌入服务不可用（无 API key）时自动降级为纯关键词路，保证功能可用
"""

import logging
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import ColumnElement, Select, case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.ai.client import LLMClient, get_llm_client
from app.core.exceptions import DomainError
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_doc import KnowledgeDoc
from app.models.script import Script

logger = logging.getLogger(__name__)

RRF_K = 60  # Reciprocal Rank Fusion 常数


@dataclass
class ScriptHit:
    script: Script
    score: float


@dataclass
class KnowledgeHit:
    chunk: KnowledgeChunk
    doc_title: str
    score: float


def _rrf_merge(rankings: list[list[uuid.UUID]]) -> dict[uuid.UUID, float]:
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    return scores


async def _embed_query(
    query: str, llm: LLMClient, user_id: uuid.UUID | None = None
) -> list[float] | None:
    """查询向量化（记账到发起用户，纳入日限额）；嵌入服务不可用时返回 None（降级纯关键词路）。"""
    try:
        vectors = await llm.embed([query], user_id=user_id)
        return vectors[0]
    except DomainError as exc:
        logger.warning("查询嵌入失败（%s），降级为纯关键词检索", exc.message)
        return None


def _query_terms(query: str, max_terms: int = 8) -> list[str]:
    """切词：空白/标点分隔，保留长度 ≥2 的词。"""
    terms = [t for t in re.split(r"[\s,，。！？;；、/|]+", query) if len(t) >= 2]
    seen: list[str] = []
    for term in terms:
        if term not in seen:
            seen.append(term)
    return seen[:max_terms]


def _keyword_score(
    columns: list[tuple[InstrumentedAttribute[str], int]], terms: list[str]
) -> ColumnElement[int]:
    """命中词数加权计分（ILIKE，locale 无关；trgm GIN 索引加速）。

    columns: [(列, 权重)]，如场景标题命中比正文命中更有信息量。
    """
    score: ColumnElement[int] = literal(0)
    for column, weight in columns:
        for term in terms:
            score = score + case((column.ilike(f"%{term}%"), weight), else_=0)
    return score


async def _ranked_ids(session: AsyncSession, stmt: Select[tuple[uuid.UUID]]) -> list[uuid.UUID]:
    return list(await session.scalars(stmt))


async def search_scripts(
    session: AsyncSession,
    query: str,
    *,
    category: str | None = None,
    top_k: int = 5,
    llm: LLMClient | None = None,
    user_id: uuid.UUID | None = None,
) -> list[ScriptHit]:
    llm = llm or get_llm_client()
    base_filter: list[ColumnElement[bool]] = [
        Script.deleted_at.is_(None),
        Script.is_active.is_(True),
    ]
    if category:
        base_filter.append(Script.category == category)

    rankings: list[list[uuid.UUID]] = []

    query_vec = await _embed_query(query, llm, user_id=user_id)
    if query_vec is not None:
        vec_stmt = (
            select(Script.id)
            .where(*base_filter, Script.embedding.is_not(None))
            .order_by(Script.embedding.cosine_distance(query_vec))
            .limit(top_k * 3)
        )
        rankings.append(await _ranked_ids(session, vec_stmt))

    terms = _query_terms(query)
    if terms:
        # 场景标题命中权重高于正文（标题是话术的语义浓缩）
        kw_score = _keyword_score([(Script.scenario, 2), (Script.content, 1)], terms)
        kw_stmt = (
            select(Script.id)
            .where(*base_filter, kw_score > 0)
            .order_by(kw_score.desc(), func.length(Script.content).asc())
            .limit(top_k * 3)
        )
        rankings.append(await _ranked_ids(session, kw_stmt))

    scores = _rrf_merge([r for r in rankings if r])
    if not scores:
        return []
    top_ids = sorted(scores, key=lambda i: scores[i], reverse=True)[:top_k]
    rows = await session.scalars(select(Script).where(Script.id.in_(top_ids)))
    by_id = {s.id: s for s in rows}
    return [ScriptHit(script=by_id[i], score=scores[i]) for i in top_ids if i in by_id]


async def search_knowledge(
    session: AsyncSession,
    query: str,
    *,
    top_k: int = 3,
    llm: LLMClient | None = None,
    user_id: uuid.UUID | None = None,
) -> list[KnowledgeHit]:
    llm = llm or get_llm_client()
    # chunk 未删 + 所属文档未删且已就绪（防止已删/失败文档的残留 chunk 进入推荐）
    ready_doc_ids = (
        select(KnowledgeDoc.id)
        .where(KnowledgeDoc.deleted_at.is_(None), KnowledgeDoc.status == "ready")
        .scalar_subquery()
    )
    base_filter: list[ColumnElement[bool]] = [
        KnowledgeChunk.deleted_at.is_(None),
        KnowledgeChunk.doc_id.in_(ready_doc_ids),
    ]

    rankings: list[list[uuid.UUID]] = []
    query_vec = await _embed_query(query, llm, user_id=user_id)
    if query_vec is not None:
        vec_stmt = (
            select(KnowledgeChunk.id)
            .where(*base_filter, KnowledgeChunk.embedding.is_not(None))
            .order_by(KnowledgeChunk.embedding.cosine_distance(query_vec))
            .limit(top_k * 3)
        )
        rankings.append(await _ranked_ids(session, vec_stmt))

    terms = _query_terms(query)
    if terms:
        kw_score = _keyword_score([(KnowledgeChunk.content, 1)], terms)
        kw_stmt = (
            select(KnowledgeChunk.id)
            .where(*base_filter, kw_score > 0)
            .order_by(kw_score.desc(), func.length(KnowledgeChunk.content).asc())
            .limit(top_k * 3)
        )
        rankings.append(await _ranked_ids(session, kw_stmt))

    scores = _rrf_merge([r for r in rankings if r])
    if not scores:
        return []
    top_ids = sorted(scores, key=lambda i: scores[i], reverse=True)[:top_k]
    rows = (
        await session.execute(
            select(KnowledgeChunk, KnowledgeDoc.title)
            .join(KnowledgeDoc, KnowledgeDoc.id == KnowledgeChunk.doc_id)
            .where(KnowledgeChunk.id.in_(top_ids))
        )
    ).all()
    by_id = {chunk.id: (chunk, title) for chunk, title in rows}
    return [
        KnowledgeHit(chunk=by_id[i][0], doc_title=by_id[i][1], score=scores[i])
        for i in top_ids
        if i in by_id
    ]
