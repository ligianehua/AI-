"""风险扫描定时任务（ARQ cron 每日 08:00；local 模式可用 scripts.run_risk_scan 手动跑）。"""

import logging
from typing import Any

from app.services import risk_service

logger = logging.getLogger(__name__)


async def risk_scan_task(ctx: dict[str, Any]) -> None:
    sessionmaker = ctx["sessionmaker"]
    async with sessionmaker() as session:
        created = await risk_service.scan_risks(session)
    logger.info("风险扫描完成，新增 %s 条提醒", created)
