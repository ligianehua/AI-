"""任务分发抽象。

TASK_MODE=arq   生产模式：入 Redis 队列，由 ARQ worker 消费（docker compose 的 worker 服务）
TASK_MODE=local 无 Redis 的开发模式：进程内 asyncio.create_task 后台执行，
                对 API 调用方同样是异步的（立即返回，稍后轮询可见结果）
"""

import asyncio
import logging
from typing import Any

from arq.connections import ArqRedis, RedisSettings, create_pool

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_pool: ArqRedis | None = None
_local_tasks: set[asyncio.Task[None]] = set()  # 持有引用防 GC


async def _get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


def _task_registry() -> dict[str, Any]:
    from app.tasks.contract import process_contract_task
    from app.tasks.discovery import run_discovery_task
    from app.tasks.embedding import embed_knowledge_doc_task, embed_script_task
    from app.tasks.forecast import forecast_snapshot_task
    from app.tasks.profile import account_profile_task
    from app.tasks.risk_scan import risk_scan_task
    from app.tasks.scoring import score_lead_task

    return {
        "score_lead_task": score_lead_task,
        "account_profile_task": account_profile_task,
        "risk_scan_task": risk_scan_task,
        "embed_script_task": embed_script_task,
        "embed_knowledge_doc_task": embed_knowledge_doc_task,
        "run_discovery_task": run_discovery_task,
        "process_contract_task": process_contract_task,
        "forecast_snapshot_task": forecast_snapshot_task,
    }


async def _run_local(task_name: str, args: tuple[Any, ...]) -> None:
    from app.core.db import get_sessionmaker

    func = _task_registry()[task_name]
    ctx = {"sessionmaker": get_sessionmaker()}
    try:
        await func(ctx, *args)
    except Exception:
        logger.exception("本地任务执行失败：%s%r", task_name, args)


async def enqueue(task_name: str, *args: Any) -> bool:
    """入队后台任务。返回是否成功。

    投递失败（如 Redis 短暂不可用）只记日志不抛异常：业务数据已 commit，
    抛错会让接口 500 但数据已存在，反而诱导用户重复提交；丢失的任务均有
    手动重试入口（线索手动重算、文档删除重传等）。调用方可按返回值补偿。
    """
    try:
        if get_settings().task_mode == "arq":
            pool = await _get_pool()
            await pool.enqueue_job(task_name, *args)
        else:
            task = asyncio.create_task(_run_local(task_name, args))
            _local_tasks.add(task)
            task.add_done_callback(_local_tasks.discard)
        return True
    except Exception:
        logger.exception("任务入队失败：%s%r（业务数据不受影响，可手动重试）", task_name, args)
        return False
