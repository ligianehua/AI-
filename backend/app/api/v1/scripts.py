import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.ai import rag
from app.ai.client import LLMClient, get_llm_client
from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.models.enums import ScriptCategory
from app.schemas.common import PageResult
from app.schemas.script import (
    RecommendRequest,
    ScriptCreate,
    ScriptOut,
    ScriptSearchHit,
    ScriptSearchRequest,
    ScriptUpdate,
)
from app.services import script_recommend, script_service

router = APIRouter(prefix="/scripts", tags=["scripts"])

PageParam = Annotated[int, Query(ge=1)]
PageSizeParam = Annotated[int, Query(ge=1, le=100)]
LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]


@router.get("", summary="话术列表（全员可读）")
async def list_scripts(
    session: SessionDep,
    current_user: CurrentUserDep,
    category: ScriptCategory | None = None,
    include_inactive: bool = False,
    page: PageParam = 1,
    page_size: PageSizeParam = 20,
) -> PageResult[ScriptOut]:
    items, total = await script_service.list_scripts(
        session,
        current_user,
        category=category,
        include_inactive=include_inactive,
        page=page,
        page_size=page_size,
    )
    return PageResult(
        items=[script_service.to_out(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", status_code=201, summary="新增话术（admin/manager，自动异步嵌入）")
async def create_script(
    body: ScriptCreate, session: SessionDep, current_user: CurrentUserDep
) -> ScriptOut:
    script = await script_service.create_script(session, current_user, body)
    return script_service.to_out(script)


@router.post("/search", summary="混合检索（向量+关键词，无嵌入时降级关键词）")
async def search_scripts(
    body: ScriptSearchRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
    llm: LLMClientDep,
) -> list[ScriptSearchHit]:
    hits = await rag.search_scripts(
        session,
        body.query,
        category=body.category,
        top_k=body.top_k,
        llm=llm,
        user_id=current_user.id,
    )
    return [
        ScriptSearchHit(script=script_service.to_out(h.script), score=round(h.score, 4))
        for h in hits
    ]


@router.post("/recommend", summary="话术推荐（SSE 流式：sources → delta* → done）")
async def recommend(
    body: RecommendRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
    llm: LLMClientDep,
) -> StreamingResponse:
    return StreamingResponse(
        script_recommend.recommend_stream(session, current_user, body, llm=llm),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.patch("/{script_id}", summary="更新话术（admin/manager；改内容重嵌入）")
async def update_script(
    script_id: uuid.UUID,
    body: ScriptUpdate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> ScriptOut:
    script = await script_service.update_script(session, current_user, script_id, body)
    return script_service.to_out(script)


@router.delete("/{script_id}", status_code=204, summary="删除话术（admin/manager，软删）")
async def delete_script(
    script_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> None:
    await script_service.delete_script(session, current_user, script_id)
