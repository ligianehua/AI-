"""providers.yaml 的加载与校验。

环境变量 AI_PROVIDERS_FILE 可覆盖配置文件路径（测试/多环境用）。
"""

import os
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_FILE = Path(__file__).parent / "providers.yaml"

# API key 在运行时按 api_key_env 从进程环境读取，这里把根目录 .env 载入进程环境
# （不覆盖已存在的环境变量；docker compose 场景由 env_file 注入，此调用是 no-op）
load_dotenv(_REPO_ROOT / ".env")


class ProviderConfig(BaseModel):
    base_url: str
    api_key_env: str
    models: dict[str, str]  # 档位 -> 模型名，如 {fast: ..., strong: ..., embedding: ...}


class RouteConfig(BaseModel):
    tier: str
    temperature: float = 0.3
    json_mode: bool = Field(default=False, alias="json")
    stream: bool = False


class ModelPricing(BaseModel):
    """元 / 1M tokens。"""

    input: Decimal = Decimal(0)
    output: Decimal = Decimal(0)


class AIConfig(BaseModel):
    providers: dict[str, ProviderConfig]
    routing: dict[str, RouteConfig]
    default_provider: str
    fallback_provider: str | None = None
    pricing: dict[str, ModelPricing] = {}

    @model_validator(mode="after")
    def _check_provider_refs(self) -> "AIConfig":
        if self.default_provider not in self.providers:
            raise ValueError(f"default_provider 未注册：{self.default_provider}")
        if self.fallback_provider is not None and self.fallback_provider not in self.providers:
            raise ValueError(f"fallback_provider 未注册：{self.fallback_provider}")
        return self


@lru_cache
def get_ai_config() -> AIConfig:
    path = Path(os.environ.get("AI_PROVIDERS_FILE") or _DEFAULT_FILE)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AIConfig.model_validate(data)
