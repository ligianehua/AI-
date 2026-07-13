"""嵌入任务：话术单条嵌入 / 知识库文档分块+批量嵌入。"""

import logging
import uuid
from typing import Any

from sqlalchemy import delete, select

from app.ai.client import get_llm_client
from app.core.exceptions import DomainError
from app.models.enums import KnowledgeDocStatus
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_doc import KnowledgeDoc
from app.models.script import Script
from app.services import knowledge_service

logger = logging.getLogger(__name__)

EMBED_BATCH = 16


async def embed_script_task(ctx: dict[str, Any], script_id: str) -> None:
    llm = ctx.get("llm") or get_llm_client()
    async with ctx["sessionmaker"]() as session:
        script = await session.scalar(select(Script).where(Script.id == uuid.UUID(script_id)))
        if script is None:
            return
        try:
            # 标题+正文一起嵌入：场景标题是话术的语义浓缩（如「决策拖延」），只嵌正文会丢关键语义
            vectors = await llm.embed([f"{script.scenario}\n{script.content}"])
        except DomainError as exc:
            logger.warning("话术 %s 嵌入失败：%s（检索将走关键词路）", script_id, exc.message)
            return
        script.embedding = vectors[0]
        await session.commit()


async def embed_knowledge_doc_task(ctx: dict[str, Any], doc_id: str) -> None:
    llm = ctx.get("llm") or get_llm_client()
    async with ctx["sessionmaker"]() as session:
        doc = await session.scalar(
            select(KnowledgeDoc).where(
                KnowledgeDoc.id == uuid.UUID(doc_id), KnowledgeDoc.deleted_at.is_(None)
            )
        )
        if doc is None:
            return  # 已删除的文档不处理，防止任务完成后"复活"软删文档
        # 幂等：任务重试/重复投递时先清掉已有 chunks，避免重复累积
        await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc.id))
        path = knowledge_service.doc_file_path(doc.id)
        if path is None:
            doc.status = KnowledgeDocStatus.FAILED
            await session.commit()
            logger.warning("知识文档 %s 源文件缺失", doc_id)
            return
        try:
            text = knowledge_service.extract_text(path)
            chunks = knowledge_service.split_chunks(text)
            if not chunks:
                raise DomainError("文档内容为空")
            vectors: list[list[float]] = []
            for i in range(0, len(chunks), EMBED_BATCH):
                vectors.extend(await llm.embed(chunks[i : i + EMBED_BATCH]))
            for index, (content, vector) in enumerate(zip(chunks, vectors, strict=True)):
                session.add(
                    KnowledgeChunk(
                        doc_id=doc.id, chunk_index=index, content=content, embedding=vector
                    )
                )
            doc.status = KnowledgeDocStatus.READY
            await session.commit()
        except DomainError as exc:
            doc.status = KnowledgeDocStatus.FAILED
            await session.commit()
            logger.warning("知识文档 %s 处理失败：%s", doc_id, exc.message)
        except Exception:
            doc.status = KnowledgeDocStatus.FAILED
            await session.commit()
            logger.exception("知识文档 %s 处理异常", doc_id)
