"""线索评分异步任务（ARQ 任务签名：ctx + 参数）。"""

import uuid
from typing import Any

from app.services import lead_scoring


async def score_lead_task(ctx: dict[str, Any], lead_id: str) -> None:
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        await lead_scoring.score_lead(session, uuid.UUID(lead_id), llm=ctx.get("llm"))
