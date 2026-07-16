"""LLM 客户端抽象：真实 Anthropic 与 Mock 规则引擎的统一接口。

engine.py 只消费 LLMEvent 事件流，两个实现完全同构。
"""
from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolUseStart:
    id: str
    name: str


@dataclass
class TurnEnd:
    stop_reason: str                      # "tool_use" | "end_turn"
    content_blocks: list = field(default_factory=list)  # API 格式 content blocks
    usage_in: int = 0
    usage_out: int = 0


LLMEvent = TextDelta | ToolUseStart | TurnEnd


@dataclass
class AnalysisResult:
    """离线会话学习分析结果"""
    resolved: bool
    summary: str
    category: str
    faq_candidates: list[dict]   # [{question, suggested_answer, confidence}]
    kb_gaps: list[dict]          # [{question, context}]
    issue_tags: list[str]        # ["扫地机器人-不开机", ...]


class LLMClient(Protocol):
    async def stream_turn(self, system: str, messages: list[dict],
                          tools: list[dict], *, mock_state: dict | None = None
                          ) -> AsyncIterator[LLMEvent]:
        """执行一轮生成，逐事件产出，最后一个事件必须是 TurnEnd"""
        ...

    def analyze_conversation(self, transcript: str) -> AnalysisResult:
        """离线分析一段会话文本，产出学习候选（同步调用，跑在后台任务里）"""
        ...

    def digest_manual(self, title: str, manual_text: str) -> list[dict]:
        """通读产品手册文本，提炼 FAQ 候选：[{question, suggested_answer, category, confidence}]"""
        ...

    def suggest_reply(self, transcript: str) -> str:
        """人工工作台：基于对话记录为客服生成一条回复建议"""
        ...

    def analyze_image(self, image_b64: str, mime: str, hint: str = "") -> str:
        """看图诊断：描述客户上传的故障照片/错误截图，输出观察结论"""
        ...

    def ocr_image(self, image_b64: str, mime: str = "image/png") -> str:
        """OCR：提取图片中的全部文字（扫描版手册用）"""
        ...

    def qa_review(self, transcript: str) -> dict:
        """会话质检：{score(0-100), dimensions{服务态度,专业准确,解决效率}, issues[], suggestion}"""
        ...
