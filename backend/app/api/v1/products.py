import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, UploadFile

from app.ai.client import LLMClient, get_llm_client
from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.core.exceptions import DomainError, PermissionDeniedError
from app.models.enums import ProductStatus, Role
from app.models.product import Product
from app.schemas.common import PageResult
from app.schemas.product import (
    ProductCompareRequest,
    ProductCreate,
    ProductOut,
    ProductSearchHit,
    ProductSearchRequest,
    ProductUpdate,
)
from app.services import product_service
from app.tasks import dispatcher
from app.tasks.product import SPEC_UPLOAD_DIR

router = APIRouter(prefix="/products", tags=["products"])

PageParam = Annotated[int, Query(ge=1)]
PageSizeParam = Annotated[int, Query(ge=1, le=100)]
LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]

ALLOWED_SUFFIXES = {".txt", ".md", ".docx"}


def _out(p: Product) -> ProductOut:
    return ProductOut(
        id=p.id,
        model_no=p.model_no,
        name=p.name,
        brand=p.brand,
        category=p.category,
        status=ProductStatus(p.status),
        specs=p.specs,
        description=p.description,
        source_doc_name=p.source_doc_name,
        has_embedding=p.embedding is not None,
        created_at=p.created_at,
    )


@router.post("", status_code=201, summary="手动创建产品（admin/manager）")
async def create_product(
    body: ProductCreate, session: SessionDep, current_user: CurrentUserDep
) -> ProductOut:
    return _out(await product_service.create_product(session, current_user, body))


@router.get("", summary="产品列表（全员可读）")
async def list_products(
    session: SessionDep,
    current_user: CurrentUserDep,
    status: ProductStatus | None = None,
    category: str | None = None,
    keyword: str | None = None,
    page: PageParam = 1,
    page_size: PageSizeParam = 20,
) -> PageResult[ProductOut]:
    items, total = await product_service.list_products(
        session, status=status, category=category, keyword=keyword, page=page, page_size=page_size
    )
    return PageResult(items=[_out(p) for p in items], total=total, page=page, page_size=page_size)


@router.post("/upload-spec", status_code=202, summary="上传规格书（异步抽取入库，admin/manager）")
async def upload_spec(
    file: UploadFile, session: SessionDep, current_user: CurrentUserDep
) -> dict[str, Any]:
    if current_user.role not in (Role.ADMIN, Role.MANAGER):
        raise PermissionDeniedError("产品库管理仅限主管和管理员")
    filename = file.filename or "规格书"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise DomainError(f"不支持的文件类型 {suffix}（支持 txt/md/docx）")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise DomainError("文件不能超过 10MB")

    token = uuid.uuid4().hex
    SPEC_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (SPEC_UPLOAD_DIR / f"{token}{suffix}").write_bytes(content)
    enqueued = await dispatcher.enqueue(
        "extract_product_task", token, Path(filename).stem[:200], str(current_user.id)
    )
    return {
        "enqueued": enqueued,
        "message": "规格书已提交，AI 正在抽取参数（约 1 分钟后刷新列表）"
        if enqueued
        else "任务提交失败，请重试",
    }


@router.post("/search", summary="自然语言检索（向量+关键词混合）")
async def search_products(
    body: ProductSearchRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
    llm: LLMClientDep,
) -> list[ProductSearchHit]:
    hits = await product_service.search_products(
        session, body.query, top_k=body.top_k, llm=llm, user_id=current_user.id
    )
    return [ProductSearchHit(product=_out(p), score=score) for p, score in hits]


@router.post("/compare", summary="参数对比（对齐矩阵 + AI 差异总结）")
async def compare_products(
    body: ProductCompareRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
    llm: LLMClientDep,
) -> dict[str, Any]:
    return await product_service.compare_products(session, current_user, body.product_ids, llm=llm)


@router.get("/{product_id}", summary="产品详情")
async def get_product(
    product_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> ProductOut:
    return _out(await product_service.get_product(session, product_id))


@router.get("/{product_id}/alternatives", summary="替代推荐（EOL 默认只推在售）")
async def find_alternatives(
    product_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
    include_eol: bool = False,
) -> dict[str, Any]:
    return await product_service.find_alternatives(session, product_id, include_eol=include_eol)


@router.patch("/{product_id}", summary="编辑产品（admin/manager，改参数自动重嵌入）")
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> ProductOut:
    return _out(await product_service.update_product(session, current_user, product_id, body))


@router.delete("/{product_id}", status_code=204, summary="删除产品（admin/manager，软删）")
async def delete_product(
    product_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> None:
    await product_service.delete_product(session, current_user, product_id)
