"""线索发现抓取任务：调 Places → 候选池入库。"""

import logging
import uuid
from typing import Any

from sqlalchemy import select

from app.core.exceptions import DomainError
from app.models.discovery_subscription import DiscoverySubscription
from app.services import discovery_service
from app.services.google_places import get_places_client

logger = logging.getLogger(__name__)


async def run_discovery_task(ctx: dict[str, Any], subscription_id: str) -> None:
    places_client = ctx.get("places") or get_places_client()
    async with ctx["sessionmaker"]() as session:
        sub = await session.scalar(
            select(DiscoverySubscription).where(
                DiscoverySubscription.id == uuid.UUID(subscription_id),
                DiscoverySubscription.deleted_at.is_(None),
            )
        )
        if sub is None or not sub.is_active:
            return
        try:
            places = await places_client.search_text(discovery_service.build_query(sub))
        except DomainError as exc:
            logger.warning("订阅 %s 抓取失败：%s", subscription_id, exc.message)
            return
        new_count = await discovery_service.ingest_places(session, sub, places)
        logger.info("订阅 %s 抓取完成：拉取 %d，新增 %d", subscription_id, len(places), new_count)
