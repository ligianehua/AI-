from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 在仓库根目录（backend 的上一级）；环境变量优先级高于文件
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "dev"
    secret_key: str = "dev-only-secret-key-change-me-in-production!"
    access_token_expire_minutes: int = 60 * 12
    cors_origins: list[str] = ["http://localhost:3000"]

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_sales"
    redis_url: str = "redis://localhost:6379/0"

    # 成本护栏：每用户每日 LLM token 限额（输入+输出），0 = 不限
    llm_daily_token_limit_per_user: int = 500_000

    # 任务模式：arq（Redis 队列，生产）| local（进程内后台执行，无 Redis 的开发环境）
    task_mode: str = "arq"

    # M0 临时引导账号（M1 落库后由 users 表取代）
    admin_email: str = "admin@example.com"
    admin_password: str = "admin123"


@lru_cache
def get_settings() -> Settings:
    return Settings()
