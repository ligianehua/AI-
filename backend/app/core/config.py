from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 在仓库根目录（backend 的上一级）；环境变量优先级高于文件
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

_DEV_SECRET = "dev-only-secret-key-change-me-in-production!"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "dev"
    secret_key: str = _DEV_SECRET
    access_token_expire_minutes: int = 60 * 12
    cors_origins: list[str] = ["http://localhost:3000"]

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_sales"
    redis_url: str = "redis://localhost:6379/0"

    # 成本护栏：每用户每日 LLM token 限额（输入+输出），0 = 不限
    llm_daily_token_limit_per_user: int = 500_000

    # 任务模式：arq（Redis 队列，生产）| local（进程内后台执行，无 Redis 的开发环境）
    task_mode: str = "arq"

    # 风险提醒阈值（天）
    risk_stale_days: int = 7  # 商机无跟进
    risk_stuck_days: int = 21  # 阶段停滞

    # 风险扫描 cron 小时（UTC）。0 = 北京时间 08:00（ARQ cron 按 UTC 计）
    risk_scan_hour_utc: int = 0

    @model_validator(mode="after")
    def _forbid_default_secret_in_prod(self) -> "Settings":
        # 生产环境禁止使用仓库公开的默认密钥（否则任何人可伪造 JWT）
        if self.app_env == "prod" and self.secret_key == _DEV_SECRET:
            raise ValueError(
                "APP_ENV=prod 时必须设置自定义 SECRET_KEY（openssl rand -hex 32），"
                "禁止使用仓库默认值"
            )
        return self

    # M0 临时引导账号（M1 落库后由 users 表取代）
    admin_email: str = "admin@example.com"
    admin_password: str = "admin123"


@lru_cache
def get_settings() -> Settings:
    return Settings()
