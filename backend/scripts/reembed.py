"""补嵌入：话术缺向量的重嵌，失败的知识文档重新处理。

适用场景：配好嵌入 API key 之前入库的数据、换嵌入模型后的全量重建。
用法：uv run python -m scripts.reembed
"""

import asyncio

from sqlalchemy import select

from app.core.db import get_engine, get_sessionmaker
from app.models.enums import KnowledgeDocStatus
from app.models.knowledge_doc import KnowledgeDoc
from app.models.script import Script
from app.tasks.embedding import embed_knowledge_doc_task, embed_script_task


async def main() -> None:
    maker = get_sessionmaker()
    ctx = {"sessionmaker": maker}
    async with maker() as session:
        script_ids = list(
            await session.scalars(
                select(Script.id).where(Script.deleted_at.is_(None), Script.embedding.is_(None))
            )
        )
        doc_ids = list(
            await session.scalars(
                select(KnowledgeDoc.id).where(
                    KnowledgeDoc.deleted_at.is_(None),
                    KnowledgeDoc.status == KnowledgeDocStatus.FAILED,
                )
            )
        )
    print(f"待嵌入话术 {len(script_ids)} 条，待重处理知识文档 {len(doc_ids)} 个")
    for script_id in script_ids:
        await embed_script_task(ctx, str(script_id))
    for doc_id in doc_ids:
        await embed_knowledge_doc_task(ctx, str(doc_id))
    async with maker() as session:
        remaining = list(
            await session.scalars(
                select(Script.id).where(Script.deleted_at.is_(None), Script.embedding.is_(None))
            )
        )
    print(f"完成。仍缺向量的话术：{len(remaining)} 条")
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())
