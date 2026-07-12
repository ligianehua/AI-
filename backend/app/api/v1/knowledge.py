import uuid
from typing import Annotated

from fastapi import APIRouter, Query, UploadFile

from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.schemas.common import PageResult
from app.schemas.knowledge import KnowledgeDocOut
from app.services import knowledge_service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

PageParam = Annotated[int, Query(ge=1)]
PageSizeParam = Annotated[int, Query(ge=1, le=100)]


@router.post("/docs", status_code=201, summary="上传知识文档（txt/md/docx，异步分块+嵌入）")
async def upload_doc(
    file: UploadFile, session: SessionDep, current_user: CurrentUserDep
) -> KnowledgeDocOut:
    content = await file.read()
    doc = await knowledge_service.upload_doc(
        session, current_user, file.filename or "untitled.txt", content
    )
    return KnowledgeDocOut.model_validate(doc)


@router.get("/docs", summary="知识文档列表")
async def list_docs(
    session: SessionDep,
    current_user: CurrentUserDep,
    page: PageParam = 1,
    page_size: PageSizeParam = 20,
) -> PageResult[KnowledgeDocOut]:
    rows, total = await knowledge_service.list_docs(
        session, current_user, page=page, page_size=page_size
    )
    items = []
    for doc, chunk_count in rows:
        out = KnowledgeDocOut.model_validate(doc)
        out.chunk_count = chunk_count
        items.append(out)
    return PageResult(items=items, total=total, page=page, page_size=page_size)


@router.delete("/docs/{doc_id}", status_code=204, summary="删除知识文档（admin/manager，软删）")
async def delete_doc(doc_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep) -> None:
    await knowledge_service.delete_doc(session, current_user, doc_id)
