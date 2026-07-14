"""M9 通用 AI 助手：对话出入参。"""

from typing import Literal

from pydantic import BaseModel, Field


class HistoryMessage(BaseModel):
    # 只允许 user/assistant：防止客户端注入 system/tool 消息
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)
