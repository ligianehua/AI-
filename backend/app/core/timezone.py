"""业务时区（PLAN §6：时间 UTC 存储、按 Asia/Shanghai 展示与计日）。

"今天到期 / 本月成交 / 每日限额"等业务日界一律按本时区计算，
避免 UTC 日界导致北京时间 00:00–07:59 的统计错位。
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

BIZ_TZ = ZoneInfo("Asia/Shanghai")


def now_utc() -> datetime:
    return datetime.now(UTC)


def biz_today(now: datetime | None = None) -> date:
    """业务口径的"今天"（Asia/Shanghai 日界）。"""
    return (now or now_utc()).astimezone(BIZ_TZ).date()


def biz_day_start_utc(now: datetime | None = None) -> datetime:
    """业务口径今日 00:00 对应的 UTC 时刻（llm_calls 等 UTC 存储字段的过滤下界）。"""
    local = (now or now_utc()).astimezone(BIZ_TZ)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def biz_month_start_utc(now: datetime | None = None) -> datetime:
    """业务口径本月 1 日 00:00 对应的 UTC 时刻。"""
    local = (now or now_utc()).astimezone(BIZ_TZ)
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
