"""LLM 供应商的测试替身（不发网络请求）。"""

from types import SimpleNamespace
from typing import Any


def completion(
    content: str,
    tokens_in: int = 10,
    tokens_out: int = 5,
    tool_calls: list[Any] | None = None,
) -> Any:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))],
        usage=SimpleNamespace(prompt_tokens=tokens_in, completion_tokens=tokens_out),
    )


def tool_call(call_id: str, name: str, arguments: str) -> Any:
    """OpenAI function tool_call 替身（completion(tool_calls=[...]) 用）。"""
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def embedding_response(vectors: list[list[float]], tokens_in: int = 7) -> Any:
    return SimpleNamespace(
        data=[SimpleNamespace(embedding=v) for v in vectors],
        usage=SimpleNamespace(prompt_tokens=tokens_in),
    )


def stream_chunk(content: str | None = None, usage: Any = None) -> Any:
    choices = (
        [SimpleNamespace(delta=SimpleNamespace(content=content))] if content is not None else []
    )
    return SimpleNamespace(choices=choices, usage=usage)


class FakeStream:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = list(chunks)

    def __aiter__(self) -> "FakeStream":
        return self

    async def __anext__(self) -> Any:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class FakeEndpoint:
    def __init__(self) -> None:
        self.responses: list[Any] = []
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeOpenAI:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=FakeEndpoint())
        self.embeddings = FakeEndpoint()
