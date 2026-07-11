"""M2 冒烟 eval：验证供应商真实连通、结构化输出与嵌入。"""

from pydantic import BaseModel, Field

from app.ai.client import LLMClient


class EchoOutput(BaseModel):
    answer: str = Field(description="回答内容")
    lang: str = Field(description="回答语言，zh 或 en")


async def test_chat_roundtrip(require_llm_keys: None) -> None:
    client = LLMClient()
    result = await client.chat(
        "ping",
        [{"role": "user", "content": "请只回复一个词：pong"}],
    )
    assert "pong" in result.content.lower()


async def test_structured_output(require_llm_keys: None) -> None:
    client = LLMClient()
    out = await client.chat_structured(
        "lead_scoring",
        [
            {
                "role": "user",
                "content": (
                    '用中文回答 1+1 等于几，并输出 JSON，格式：{"answer": "回答内容", "lang": "zh"}'
                ),
            }
        ],
        EchoOutput,
    )
    assert out.lang == "zh"
    assert "2" in out.answer or "二" in out.answer


async def test_embedding(require_llm_keys: None) -> None:
    client = LLMClient()
    vectors = await client.embed(["销售管理系统", "客户关系管理"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 1024
