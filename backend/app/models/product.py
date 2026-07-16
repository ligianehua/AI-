import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AppModel
from app.models.enums import ProductStatus


class Product(AppModel):
    """产品库（公司公共资产：全员可读，admin/manager 可管理）。

    specs 为参数键值对（LLM 从规格书抽取或手动维护）；embedding 用
    「型号+名称+参数」拼接文本生成，支撑自然语言检索与替代挖掘。
    model_no 部分唯一：同型号重复上传规格书幂等更新。
    """

    __tablename__ = "products"

    model_no: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(20),
        default=ProductStatus.ACTIVE,
        server_default=ProductStatus.ACTIVE.value,
        index=True,
    )
    specs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    description: Mapped[str | None] = mapped_column(Text)
    source_doc_name: Mapped[str | None] = mapped_column(String(200))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (
        Index(
            "uq_products_model_no_active",
            "model_no",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
