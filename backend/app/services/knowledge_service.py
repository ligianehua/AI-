"""知识库：上传（txt/md/docx）→ data/uploads → 异步分块+嵌入。"""

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError, NotFoundError, PermissionDeniedError
from app.models.enums import KnowledgeDocStatus, Role
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_doc import KnowledgeDoc
from app.models.user import User
from app.tasks import dispatcher

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "data" / "uploads"
ALLOWED_SUFFIXES = {".txt", ".md", ".docx"}
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100


def _require_manager(actor: User) -> None:
    if actor.role not in (Role.ADMIN, Role.MANAGER):
        raise PermissionDeniedError("知识库管理仅限主管和管理员")


async def upload_doc(
    session: AsyncSession, actor: User, filename: str, content: bytes
) -> KnowledgeDoc:
    _require_manager(actor)
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise DomainError(f"不支持的文件类型 {suffix}（支持 txt/md/docx）")
    if len(content) > 10 * 1024 * 1024:
        raise DomainError("文件不能超过 10MB")

    doc = KnowledgeDoc(title=Path(filename).stem[:200], status=KnowledgeDocStatus.PROCESSING)
    session.add(doc)
    await session.commit()
    await session.refresh(doc)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / f"{doc.id}{suffix}").write_bytes(content)

    await dispatcher.enqueue("embed_knowledge_doc_task", str(doc.id))
    return doc


async def list_docs(
    session: AsyncSession, actor: User, *, page: int = 1, page_size: int = 20
) -> tuple[list[tuple[KnowledgeDoc, int]], int]:
    stmt = select(KnowledgeDoc).where(KnowledgeDoc.deleted_at.is_(None))
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    docs = list(
        await session.scalars(
            stmt.order_by(KnowledgeDoc.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    )
    count_rows = (
        await session.execute(
            select(KnowledgeChunk.doc_id, func.count())
            .where(
                KnowledgeChunk.doc_id.in_([d.id for d in docs] or [None]),
                KnowledgeChunk.deleted_at.is_(None),
            )
            .group_by(KnowledgeChunk.doc_id)
        )
    ).all()
    counts: dict[uuid.UUID, int] = {row[0]: int(row[1]) for row in count_rows}
    return [(d, counts.get(d.id, 0)) for d in docs], total


async def delete_doc(session: AsyncSession, actor: User, doc_id: uuid.UUID) -> None:
    _require_manager(actor)
    doc = await session.scalar(
        select(KnowledgeDoc).where(KnowledgeDoc.id == doc_id, KnowledgeDoc.deleted_at.is_(None))
    )
    if doc is None:
        raise NotFoundError("文档不存在")
    now = datetime.now(UTC)
    doc.deleted_at = now
    chunks = await session.scalars(select(KnowledgeChunk).where(KnowledgeChunk.doc_id == doc.id))
    for chunk in chunks:
        chunk.deleted_at = now
    await session.commit()


# ---------- 文本抽取与分块（任务侧调用） ----------


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".docx":
        from docx import Document

        document = Document(str(path))
        return "\n".join(p.text for p in document.paragraphs)
    raise DomainError(f"不支持的文件类型：{suffix}")


def split_chunks(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """按段落优先切块，超长段落滑窗切分。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    chunks: list[str] = []
    buffer = ""
    for para in paragraphs:
        if len(buffer) + len(para) + 1 <= size:
            buffer = f"{buffer}\n{para}".strip()
            continue
        if buffer:
            chunks.append(buffer)
        while len(para) > size:
            chunks.append(para[:size])
            para = para[size - overlap :]
        buffer = para
    if buffer:
        chunks.append(buffer)
    return chunks


def doc_file_path(doc_id: uuid.UUID) -> Path | None:
    for suffix in ALLOWED_SUFFIXES:
        candidate = UPLOAD_DIR / f"{doc_id}{suffix}"
        if candidate.exists():
            return candidate
    return None
