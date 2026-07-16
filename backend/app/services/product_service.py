"""M13 产品分析助手：产品库 CRUD / 混合检索 / 参数对比 / 替代挖掘。

产品库是公司公共资产：全员可读，admin/manager 可管理（同话术库权限模型）。
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute  # noqa: TC002  # cast 目标类型

from app.ai.client import LLMClient, get_llm_client
from app.ai.prompt_loader import render_prompt
from app.ai.rag import _query_terms
from app.ai.schemas import ProductCompareOutput
from app.core.exceptions import DomainError, NotFoundError, PermissionDeniedError
from app.models.enums import LlmTaskType, ProductStatus, Role
from app.models.product import Product
from app.models.user import User
from app.schemas.product import ProductCreate, ProductUpdate
from app.tasks import dispatcher

ALLOWED_SUFFIXES = {".txt", ".md", ".docx"}


def _require_manager(actor: User) -> None:
    if actor.role not in (Role.ADMIN, Role.MANAGER):
        raise PermissionDeniedError("产品库管理仅限主管和管理员")


def embedding_text(model_no: str, name: str, specs: dict[str, Any]) -> str:
    """向量索引文本：型号+名称+参数（检索与替代挖掘的语义底座）。"""
    spec_part = "；".join(f"{k}:{v}" for k, v in specs.items())
    return f"{model_no} {name}\n{spec_part}"


async def _embed_product(product: Product, llm: LLMClient) -> None:
    vectors = await llm.embed([embedding_text(product.model_no, product.name, product.specs)])
    product.embedding = vectors[0]


# ---------- CRUD ----------


async def create_product(session: AsyncSession, actor: User, payload: ProductCreate) -> Product:
    _require_manager(actor)
    dup = await session.scalar(
        select(Product).where(Product.model_no == payload.model_no, Product.deleted_at.is_(None))
    )
    if dup is not None:
        raise DomainError(f"型号 {payload.model_no} 已存在（如需更新请编辑该产品）")
    product = Product(**payload.model_dump(), created_by=actor.id)
    session.add(product)
    await session.commit()
    await session.refresh(product)
    await dispatcher.enqueue("embed_product_task", str(product.id))
    return product


async def list_products(
    session: AsyncSession,
    *,
    status: ProductStatus | None = None,
    category: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Product], int]:
    filters: list[ColumnElement[bool]] = [Product.deleted_at.is_(None)]
    if status is not None:
        filters.append(Product.status == status)
    if category:
        filters.append(Product.category == category)
    if keyword:
        kw = f"%{keyword}%"
        filters.append(Product.model_no.ilike(kw) | Product.name.ilike(kw))
    total = int(
        await session.scalar(select(func.count()).select_from(Product).where(*filters)) or 0
    )
    rows = list(
        await session.scalars(
            select(Product)
            .where(*filters)
            .order_by(Product.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    )
    return rows, total


async def get_product(session: AsyncSession, product_id: uuid.UUID) -> Product:
    product = await session.scalar(
        select(Product).where(Product.id == product_id, Product.deleted_at.is_(None))
    )
    if product is None:
        raise NotFoundError("产品不存在")
    return product


async def update_product(
    session: AsyncSession, actor: User, product_id: uuid.UUID, payload: ProductUpdate
) -> Product:
    _require_manager(actor)
    product = await get_product(session, product_id)
    data = payload.model_dump(exclude_unset=True)
    reembed = any(k in data for k in ("model_no", "name", "specs"))
    for key, value in data.items():
        setattr(product, key, value)
    await session.commit()
    await session.refresh(product)
    if reembed:
        await dispatcher.enqueue("embed_product_task", str(product.id))
    return product


async def delete_product(session: AsyncSession, actor: User, product_id: uuid.UUID) -> None:
    _require_manager(actor)
    product = await get_product(session, product_id)
    product.deleted_at = datetime.now(UTC)
    await session.commit()


# ---------- 自然语言混合检索（向量 + 关键词，RRF 融合，复用 rag 设计） ----------


async def search_products(
    session: AsyncSession,
    query: str,
    *,
    top_k: int = 5,
    llm: LLMClient | None = None,
    user_id: uuid.UUID | None = None,
) -> list[tuple[Product, float]]:
    from app.ai import rag

    llm = llm or get_llm_client()
    base_filter: list[ColumnElement[bool]] = [Product.deleted_at.is_(None)]
    rankings: list[list[uuid.UUID]] = []

    query_vec = await rag._embed_query(query, llm, user_id=user_id)
    if query_vec is not None:
        vec_stmt = (
            select(Product.id)
            .where(*base_filter, Product.embedding.is_not(None))
            .order_by(Product.embedding.cosine_distance(query_vec))
            .limit(top_k * 3)
        )
        rankings.append(list(await session.scalars(vec_stmt)))

    # description 列可空，但 ILIKE 对 NULL 自然不命中——类型层面 cast 即可
    kw_columns = cast(
        "list[tuple[InstrumentedAttribute[str], int]]",
        [(Product.model_no, 2), (Product.name, 2), (Product.description, 1)],
    )
    terms = _query_terms(query)
    if terms:
        terms = await rag._discriminative_terms(session, terms, kw_columns, base_filter)
    if terms:
        kw_score = rag._keyword_score(kw_columns, terms)
        kw_stmt = (
            select(Product.id)
            .where(*base_filter, kw_score > 0)
            .order_by(kw_score.desc())
            .limit(top_k * 3)
        )
        rankings.append(list(await session.scalars(kw_stmt)))

    scores = rag._rrf_merge([r for r in rankings if r])
    if not scores:
        return []
    top_ids = sorted(scores, key=lambda i: scores[i], reverse=True)[:top_k]
    rows = await session.scalars(select(Product).where(Product.id.in_(top_ids)))
    by_id = {p.id: p for p in rows}
    return [(by_id[i], round(scores[i], 4)) for i in top_ids if i in by_id]


# ---------- 参数对比（代码对齐矩阵 + LLM 差异总结） ----------


def build_compare_matrix(products: list[Product]) -> dict[str, Any]:
    """对齐全部 spec keys 生成矩阵；'—' 表示该产品无此参数。"""
    all_keys: list[str] = []
    for p in products:
        for k in p.specs:
            if k not in all_keys:
                all_keys.append(k)
    return {
        "products": [
            {
                "model_no": p.model_no,
                "name": p.name,
                "brand": p.brand or "—",
                "status": p.status,
            }
            for p in products
        ],
        "rows": [
            {"param": key, "values": [str(p.specs.get(key, "—")) for p in products]}
            for key in all_keys
        ],
    }


async def compare_products(
    session: AsyncSession,
    actor: User,
    product_ids: list[uuid.UUID],
    llm: LLMClient | None = None,
) -> dict[str, Any]:
    if not 2 <= len(product_ids) <= 4:
        raise DomainError("对比需要选择 2-4 个产品")
    llm = llm or get_llm_client()
    products = [await get_product(session, pid) for pid in product_ids]
    matrix = build_compare_matrix(products)

    analysis: dict[str, Any] | None = None
    analysis_note: str | None = None
    try:
        out = await llm.chat_structured(
            LlmTaskType.PRODUCT_COMPARE,
            [
                {
                    "role": "user",
                    "content": render_prompt(
                        "product_compare.j2",
                        matrix=json.dumps(matrix, ensure_ascii=False, indent=1),
                    ),
                }
            ],
            ProductCompareOutput,
            user_id=actor.id,
        )
        analysis = out.model_dump()
    except DomainError as exc:
        analysis_note = f"AI 差异总结暂不可用（{exc.message}），对比矩阵不受影响"
    return {"matrix": matrix, "analysis": analysis, "analysis_note": analysis_note}


# ---------- 替代挖掘（向量相似；EOL 型号默认只推在售替代） ----------


async def find_alternatives(
    session: AsyncSession,
    product_id: uuid.UUID,
    *,
    top_k: int = 5,
    include_eol: bool = False,
) -> dict[str, Any]:
    target = await get_product(session, product_id)
    if target.embedding is None:
        raise DomainError("该产品尚未生成向量索引（请稍后重试或重新保存产品）")

    filters: list[ColumnElement[bool]] = [
        Product.deleted_at.is_(None),
        Product.id != target.id,
        Product.embedding.is_not(None),
    ]
    # 停产型号找替代 → 默认只推在售；在售产品找同类 → 默认也排除停产（可放开）
    if not include_eol:
        filters.append(Product.status == ProductStatus.ACTIVE)

    distance = Product.embedding.cosine_distance(target.embedding)
    rows = (
        await session.execute(
            select(Product, distance.label("dist")).where(*filters).order_by(distance).limit(top_k)
        )
    ).all()

    def _spec_diff(candidate: Product) -> list[str]:
        diffs = []
        for key, val in target.specs.items():
            other = candidate.specs.get(key)
            if other is not None and str(other) != str(val):
                diffs.append(f"{key}: {val} → {other}")
        return diffs[:5]

    return {
        "target": {"id": str(target.id), "model_no": target.model_no, "status": target.status},
        "alternatives": [
            {
                "id": str(p.id),
                "model_no": p.model_no,
                "name": p.name,
                "brand": p.brand,
                "status": p.status,
                "similarity": round(1 - float(dist), 4),
                "spec_diffs": _spec_diff(p),
            }
            for p, dist in rows
        ],
    }
