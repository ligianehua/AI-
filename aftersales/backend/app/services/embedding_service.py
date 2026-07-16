"""向量语义检索：embedding 生成 + 余弦相似度 + RRF 混合融合。

仅在 OpenAI 兼容 / Anthropic 之外可用 embeddings 端点时启用；
不可用（如演示模式或端点报错）时静默降级为纯 FTS 检索。
"""
import json
import math

from ..config import settings

EMBED_MODEL = "text-embedding-v4"
EMBED_BATCH = 10  # DashScope 系接口单次批量上限
_client = None
_available: bool | None = None  # None=未探测


def _get_client():
    global _client
    if _client is None and settings.openai_api_key:
        from openai import OpenAI
        _client = OpenAI(api_key=settings.openai_api_key,
                         base_url=settings.openai_base_url, timeout=60)
    return _client


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """批量向量化（内部按 EMBED_BATCH 分批）；不可用返回 None（调用方降级）"""
    global _available
    if not texts:
        return []
    if _available is False:
        return None
    client = _get_client()
    if client is None:
        _available = False
        return None
    out: list[list[float]] = []
    try:
        for i in range(0, len(texts), EMBED_BATCH):
            resp = client.embeddings.create(
                model=EMBED_MODEL,
                input=[t[:2000] for t in texts[i:i + EMBED_BATCH]])
            out.extend(d.embedding for d in resp.data)
        _available = True
        return out
    except Exception:
        if _available is None:
            _available = False  # 首次探测即失败：端点不可用，后续快速跳过
        return None  # 已探测可用时视为瞬时错误，本次降级但不永久关闭


def embed_one(text: str) -> list[float] | None:
    vecs = embed_texts([text])
    return vecs[0] if vecs else None


def to_json(vec: list[float] | None) -> str | None:
    return json.dumps([round(x, 6) for x in vec]) if vec else None


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def vector_rank(query_vec: list[float], candidates: list[tuple[int, str]],
                top_k: int = 10, min_sim: float = 0.35) -> list[tuple[int, float]]:
    """candidates: [(id, embedding_json)] -> [(id, 相似度)] 降序"""
    scored = []
    for cid, emb_json in candidates:
        if not emb_json:
            continue
        try:
            vec = json.loads(emb_json)
        except json.JSONDecodeError:
            continue
        sim = cosine(query_vec, vec)
        if sim >= min_sim:
            scored.append((cid, round(sim, 4)))
    scored.sort(key=lambda kv: -kv[1])
    return scored[:top_k]


def rrf_merge(rank_lists: list[list[int]], top_k: int, k: int = 60) -> list[int]:
    """Reciprocal Rank Fusion：融合多路召回的排名"""
    scores: dict[int, float] = {}
    for ranks in rank_lists:
        for pos, cid in enumerate(ranks):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + pos + 1)
    return [cid for cid, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:top_k]]
