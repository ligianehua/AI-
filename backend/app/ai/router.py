"""任务类型 → 模型档位 → 供应商解析。"""

from dataclasses import dataclass

from app.ai.config import AIConfig, ProviderConfig, get_ai_config
from app.core.exceptions import LLMUnavailableError


@dataclass(frozen=True)
class ResolvedRoute:
    provider_name: str
    provider: ProviderConfig
    model: str
    temperature: float
    json_mode: bool
    stream: bool


def resolve(
    task_type: str, *, use_fallback: bool = False, cfg: AIConfig | None = None
) -> ResolvedRoute | None:
    """解析任务路由。

    - 供应商顺序：default → fallback；缺该档位的供应商自动跳过
      （例如 embedding 档位只有 qwen 提供，则 embedding 任务直接落到 qwen）。
    - use_fallback=True 时跳过首选供应商；无可用降级目标返回 None。
    """
    cfg = cfg or get_ai_config()
    route = cfg.routing.get(task_type)
    if route is None:
        raise LLMUnavailableError(f"未配置任务路由：{task_type}")

    order = [cfg.default_provider]
    if cfg.fallback_provider and cfg.fallback_provider != cfg.default_provider:
        order.append(cfg.fallback_provider)

    candidates = [name for name in order if route.tier in cfg.providers[name].models]
    if use_fallback:
        candidates = candidates[1:]
    if not candidates:
        if use_fallback:
            return None
        raise LLMUnavailableError(f"没有供应商提供档位：{route.tier}")

    name = candidates[0]
    provider = cfg.providers[name]
    return ResolvedRoute(
        provider_name=name,
        provider=provider,
        model=provider.models[route.tier],
        temperature=route.temperature,
        json_mode=route.json_mode,
        stream=route.stream,
    )
