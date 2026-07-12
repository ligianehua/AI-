"""手动执行一次风险扫描（local 模式没有 cron 时用）。

用法：uv run python -m scripts.run_risk_scan
"""

import asyncio

from app.core.db import get_engine, get_sessionmaker
from app.services import risk_service


async def main() -> None:
    async with get_sessionmaker()() as session:
        created = await risk_service.scan_risks(session)
    await get_engine().dispose()
    print(f"风险扫描完成，新增 {created} 条提醒")


if __name__ == "__main__":
    asyncio.run(main())
