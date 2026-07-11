"""客户画像生成异步任务。以客户 owner 的身份执行（画像输入即其可见域内数据）。"""

import logging
import uuid
from typing import Any

from sqlalchemy import select

from app.models.account import Account
from app.models.user import User
from app.services import account_profile

logger = logging.getLogger(__name__)


async def account_profile_task(ctx: dict[str, Any], account_id: str) -> None:
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        account = await session.scalar(select(Account).where(Account.id == uuid.UUID(account_id)))
        if account is None:
            logger.warning("画像任务：客户 %s 不存在", account_id)
            return
        owner = await session.scalar(select(User).where(User.id == account.owner_id))
        if owner is None:
            logger.warning("画像任务：客户 %s 的负责人不存在", account_id)
            return
        await account_profile.generate_profile(session, owner, account.id, llm=ctx.get("llm"))
