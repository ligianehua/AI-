"""ARQ worker 入口：uv run arq app.tasks.worker.WorkerSettings

docker compose 中由 worker 服务运行；cron：每日 08:00 风险扫描。
"""

from typing import Any

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.tasks.contract import process_contract_task
from app.tasks.discovery import run_discovery_task
from app.tasks.embedding import embed_knowledge_doc_task, embed_script_task
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
    functions = [
        score_lead_task,
        account_profile_task,
        risk_scan_task,
        embed_script_task,
        embed_knowledge_doc_task,
        run_discovery_task,
        process_contract_task,
    ]
    # ARQ cron 按 UTC 计时：默认 hour=0 即北京时间 08:00（RISK_SCAN_HOUR_UTC 可调）
    cron_jobs = [cron(risk_scan_task, hour=get_settings().risk_scan_hour_utc, minute=0)]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 300
