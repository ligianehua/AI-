"""Google Places API (New) 客户端——M8 线索发现的数据源。

只封装 Text Search 一个端点；密钥走 GOOGLE_MAPS_API_KEY（.env）。
错误一律转领域异常（中文提示），禁止把 Google 的 500/403 直接漏成本系统 500。
后续接入 Apollo.io / 邓白氏时按本接口形状（search → list[PlaceResult]）扩展。
"""

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import DomainError

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
# 只取候选池需要的字段：字段越少计费 SKU 越低
_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.internationalPhoneNumber,places.websiteUri,places.types"
)
_TIMEOUT_S = 30
_MAX_PAGE_SIZE = 20  # Places searchText 单页上限


@dataclass
class PlaceResult:
    place_id: str
    name: str
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class GooglePlacesClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key if api_key is not None else get_settings().google_maps_api_key

    async def search_text(self, query: str, max_results: int = _MAX_PAGE_SIZE) -> list[PlaceResult]:
        """文本搜索商户。max_results ≤ 20（单页；MVP 不翻页，控制配额）。"""
        if not self._api_key:
            raise DomainError("未配置 GOOGLE_MAPS_API_KEY，线索发现不可用（见 .env.example）")
        payload = {"textQuery": query, "maxResultCount": min(max_results, _MAX_PAGE_SIZE)}
        headers = {"X-Goog-Api-Key": self._api_key, "X-Goog-FieldMask": _FIELD_MASK}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                resp = await client.post(_SEARCH_URL, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise DomainError("Google Places 请求失败（网络/超时），请稍后重试") from exc
        if resp.status_code != 200:
            logger.warning("Places API %s：%s", resp.status_code, resp.text[:500])
            raise DomainError(
                f"Google Places 调用失败（HTTP {resp.status_code}），请检查密钥与配额"
            )
        places = resp.json().get("places", [])
        return [
            PlaceResult(
                place_id=p["id"],
                name=(p.get("displayName") or {}).get("text") or "（未知名称）",
                address=p.get("formattedAddress"),
                phone=p.get("internationalPhoneNumber"),
                website=p.get("websiteUri"),
                raw=p,
            )
            for p in places
            if p.get("id")
        ]


@lru_cache
def get_places_client() -> GooglePlacesClient:
    """应用级单例（FastAPI 依赖用；测试用 dependency_overrides / ctx 注入替换）。"""
    return GooglePlacesClient()
