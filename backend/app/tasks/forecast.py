"""预测快照任务：每周一 cron（UTC 01:00 = 北京 09:00）+ 手动触发。"""

import logging
from typing import Any

from app.services import forecast_service

logger = logging.getLogger(__name__)


async def forecast_snapshot_task(ctx: dict[str, Any]) -> None:
    async with ctx["sessionmaker"]() as session:
        count = await forecast_service.take_snapshots(session)
        logger.info("预测快照完成：%d 个 owner", count)
