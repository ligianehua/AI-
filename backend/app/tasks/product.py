"""产品任务：规格书抽取入库（幂等 upsert）+ 产品向量生成。"""

import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.ai.client import get_llm_client
from app.ai.prompt_loader import render_prompt
from app.ai.schemas import ProductExtractOutput
from app.core.exceptions import DomainError
from app.models.enums import LlmTaskType, ProductStatus
from app.models.product import Product
from app.services import knowledge_service
from app.services.product_service import embedding_text

logger = logging.getLogger(__name__)

SPEC_UPLOAD_DIR = knowledge_service.UPLOAD_DIR / "specs"
MAX_SPEC_CHARS = 30_000


def spec_file_path(token: str) -> Path | None:
    for suffix in (".txt", ".md", ".docx"):
        candidate = SPEC_UPLOAD_DIR / f"{token}{suffix}"
        if candidate.exists():
            return candidate
    return None


async def extract_product_task(
    ctx: dict[str, Any], upload_token: str, source_name: str, created_by: str
) -> None:
    """规格书 → LLM 结构化抽取 → 按 model_no 幂等 upsert → 嵌入。"""
    llm = ctx.get("llm") or get_llm_client()
    path = spec_file_path(upload_token)
    if path is None:
        logger.warning("规格书文件缺失：%s", upload_token)
        return
    async with ctx["sessionmaker"]() as session:
        try:
            text = knowledge_service.extract_text(path).strip()
            if not text:
                raise DomainError("规格书内容为空")
            if len(text) > MAX_SPEC_CHARS:
                text = text[:MAX_SPEC_CHARS]

            out = await llm.chat_structured(
                LlmTaskType.PRODUCT_EXTRACT,
                [
                    {
                        "role": "user",
                        "content": render_prompt("product_extract.j2", spec_text=text),
                    }
                ],
                ProductExtractOutput,
                user_id=uuid.UUID(created_by),
            )
            if out.model_no == "未提及":
                logger.warning("规格书 %s 未识别出型号，跳过入库", source_name)
                return

            existing = await session.scalar(
                select(Product).where(
                    Product.model_no == out.model_no, Product.deleted_at.is_(None)
                )
            )
            if existing is not None:
                existing.name = out.name
                existing.brand = None if out.brand == "未提及" else out.brand
                existing.category = out.category
                existing.specs = out.specs
                existing.description = out.description
                existing.source_doc_name = source_name
                product = existing
            else:
                product = Product(
                    model_no=out.model_no,
                    name=out.name,
                    brand=None if out.brand == "未提及" else out.brand,
                    category=out.category,
                    status=ProductStatus.ACTIVE,
                    specs=out.specs,
                    description=out.description,
                    source_doc_name=source_name,
                    created_by=uuid.UUID(created_by),
                )
                session.add(product)
                await session.flush()

            vectors = await llm.embed(
                [embedding_text(product.model_no, product.name, product.specs)]
            )
            product.embedding = vectors[0]
            await session.commit()
            logger.info("规格书 %s 抽取入库：%s", source_name, product.model_no)
        except DomainError as exc:
            logger.warning("规格书 %s 处理失败：%s", source_name, exc.message)
        except Exception:
            logger.exception("规格书 %s 处理异常", source_name)


async def embed_product_task(ctx: dict[str, Any], product_id: str) -> None:
    llm = ctx.get("llm") or get_llm_client()
    async with ctx["sessionmaker"]() as session:
        product = await session.scalar(select(Product).where(Product.id == uuid.UUID(product_id)))
        if product is None:
            return
        try:
            vectors = await llm.embed(
                [embedding_text(product.model_no, product.name, product.specs)]
            )
        except DomainError as exc:
            logger.warning("产品 %s 嵌入失败：%s（检索走关键词路）", product_id, exc.message)
            return
        product.embedding = vectors[0]
        await session.commit()
