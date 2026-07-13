"""知识库测试：上传、权限、分块、嵌入任务全流程（fake embed）、失败路径。"""

import io
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.ai.client import LLMClient
from app.models import KnowledgeChunk, KnowledgeDoc
from app.services.knowledge_service import split_chunks
from app.tasks import dispatcher
from app.tasks.embedding import embed_knowledge_doc_task
from tests.conftest import RoleUsers
from tests.fake_llm import FakeOpenAI, embedding_response

LoginFn = Callable[[str], Awaitable[dict[str, str]]]


@pytest.fixture(autouse=True)
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[Any, ...]]]:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fake_enqueue(task_name: str, *args: Any) -> bool:
        calls.append((task_name, args))
        return True

    monkeypatch.setattr(dispatcher, "enqueue", fake_enqueue)
    return calls


def test_split_chunks_paragraph_and_overlap() -> None:
    text = "第一段。\n\n第二段。\n\n" + "长" * 1200
    chunks = split_chunks(text, size=500, overlap=100)
    assert len(chunks) >= 3
    assert "第一段" in chunks[0]
    assert all(len(c) <= 500 for c in chunks)


async def test_upload_permissions_and_flow(
    client: AsyncClient,
    session: AsyncSession,
    engine: AsyncEngine,
    roles: RoleUsers,
    login: LoginFn,
    llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
    enqueued: list[tuple[str, tuple[Any, ...]]],
) -> None:
    para1 = "产品支持私有化部署，提供完整的部署文档与运维支持。" * 15  # ≈360 字
    para2 = "数据加密存储，符合等保二级要求，支持审计日志导出。" * 15
    content = f"{para1}\n\n{para2}".encode()

    # sales 不能上传
    resp = await client.post(
        "/api/v1/knowledge/docs",
        files={"file": ("产品FAQ.txt", io.BytesIO(content), "text/plain")},
        headers=await login("sales_a@test.cn"),
    )
    assert resp.status_code == 403

    # 不支持的类型
    resp = await client.post(
        "/api/v1/knowledge/docs",
        files={"file": ("bad.pdf", io.BytesIO(b"x"), "application/pdf")},
        headers=await login("manager_a@test.cn"),
    )
    assert resp.status_code == 400

    # manager 上传成功 → processing + 任务入队
    resp = await client.post(
        "/api/v1/knowledge/docs",
        files={"file": ("产品FAQ.txt", io.BytesIO(content), "text/plain")},
        headers=await login("manager_a@test.cn"),
    )
    assert resp.status_code == 201, resp.text
    doc_id = resp.json()["id"]
    assert resp.json()["status"] == "processing"
    assert enqueued == [("embed_knowledge_doc_task", (doc_id,))]

    # 执行嵌入任务（fake embed 返回 2 个向量）
    fakes["qwen"].embeddings.responses = [embedding_response([[0.1] * 1024, [0.2] * 1024])]
    maker = async_sessionmaker(engine, expire_on_commit=False)
    await embed_knowledge_doc_task({"sessionmaker": maker, "llm": llm}, doc_id)

    doc = await session.scalar(select(KnowledgeDoc).where(KnowledgeDoc.title == "产品FAQ"))
    assert doc is not None and doc.status == "ready"
    chunks = list(
        await session.scalars(select(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc.id))
    )
    assert len(chunks) == 2
    assert chunks[0].embedding is not None

    # 列表可见 chunk_count；删除后消失
    headers_m = await login("manager_a@test.cn")
    resp = await client.get("/api/v1/knowledge/docs", headers=headers_m)
    item = resp.json()["items"][0]
    assert item["chunk_count"] == 2

    resp = await client.delete(f"/api/v1/knowledge/docs/{doc_id}", headers=headers_m)
    assert resp.status_code == 204
    resp = await client.get("/api/v1/knowledge/docs", headers=headers_m)
    assert resp.json()["total"] == 0


async def test_embed_task_failure_marks_failed(
    client: AsyncClient,
    session: AsyncSession,
    engine: AsyncEngine,
    roles: RoleUsers,
    login: LoginFn,
    llm: LLMClient,
    fakes: dict[str, FakeOpenAI],
) -> None:
    """嵌入服务不可用 → 文档标记 failed（不静默）。"""
    resp = await client.post(
        "/api/v1/knowledge/docs",
        files={"file": ("案例.md", io.BytesIO("# 案例\n内容".encode()), "text/markdown")},
        headers=await login("admin@test.cn"),
    )
    doc_id = resp.json()["id"]

    # fakes 无 embeddings 响应 → embed 抛 LLMUnavailable → failed
    maker = async_sessionmaker(engine, expire_on_commit=False)
    await embed_knowledge_doc_task({"sessionmaker": maker, "llm": llm}, doc_id)

    doc = await session.scalar(select(KnowledgeDoc).where(KnowledgeDoc.title == "案例"))
    assert doc is not None and doc.status == "failed"
