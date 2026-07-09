from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    secret_key: str = "dev-only-secret-key-change-me-in-production!"
    access_token_expire_minutes: int = 60 * 12
    cors_origins: list[str] = ["http://localhost:3000"]

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_sales"
    redis_url: str = "redis://localhost:6379/0"

    # M0 临时引导账号（M1 落库后由 users 表取代）
    admin_email: str = "admin@example.com"
    admin_password: str = "admin123"


@lru_cache
def get_settings() -> Settings:
    return Settings()
