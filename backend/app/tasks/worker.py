"""ARQ worker 入口：uv run arq app.tasks.worker.WorkerSettings

docker compose 中由 worker 服务运行；cron：每日 08:00 风险扫描。
"""

from typing import Any

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.tasks.profile import account_profile_task
from app.tasks.risk_scan import risk_scan_task
from app.tasks.scoring import score_lead_task


async def startup(ctx: dict[str, Any]) -> None:
    from app.core.db import get_sessionmaker

    ctx["sessionmaker"] = get_sessionmaker()


async def shutdown(ctx: dict[str, Any]) -> None:
    from app.core.db import get_engine

    await get_engine().dispose()


class WorkerSettings:
    functions = [score_lead_task, account_profile_task, risk_scan_task]
    cron_jobs = [cron(risk_scan_task, hour=8, minute=0)]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 300
