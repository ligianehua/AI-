"""M13 产品库：出入参。"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ProductStatus
from app.schemas.common import forbid_explicit_null


class ProductCreate(BaseModel):
    model_no: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    brand: str | None = Field(None, max_length=100)
    category: str | None = Field(None, max_length=100)
    status: ProductStatus = ProductStatus.ACTIVE
    specs: dict[str, str] = Field(default_factory=dict)
    description: str | None = Field(None, max_length=4000)


class ProductUpdate(BaseModel):
    model_no: str | None = Field(None, min_length=1, max_length=100)
    name: str | None = Field(None, min_length=1, max_length=200)
    brand: str | None = Field(None, max_length=100)
    category: str | None = Field(None, max_length=100)
    status: ProductStatus | None = None
    specs: dict[str, str] | None = None
    description: str | None = Field(None, max_length=4000)

    _no_null = forbid_explicit_null("model_no", "name", "status", "specs")


class ProductOut(BaseModel):
    id: uuid.UUID
    model_no: str
    name: str
    brand: str | None
    category: str | None
    status: ProductStatus
    specs: dict[str, Any]
    description: str | None
    source_doc_name: str | None
    has_embedding: bool
    created_at: datetime


class ProductSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(5, ge=1, le=20)


class ProductSearchHit(BaseModel):
    product: ProductOut
    score: float


class ProductCompareRequest(BaseModel):
    product_ids: list[uuid.UUID] = Field(min_length=2, max_length=4)
