"""真实 Anthropic API 客户端：claude-opus-4-8 + adaptive thinking + 流式 + 提示缓存"""
import json
from typing import AsyncIterator

import anthropic

from ..config import settings
from .base import AnalysisResult, LLMEvent, TextDelta, ToolUseStart, TurnEnd

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "resolved": {"type": "boolean"},
        "summary": {"type": "string"},
        "category": {"type": "string",
                     "enum": ["产品使用", "故障排查", "退换货政策", "保修条款", "物流", "其他"]},
        "faq_candidates": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {"question": {"type": "string"},
                                     "suggested_answer": {"type": "string"},
                                     "confidence": {"type": "number"}},
                      "required": ["question", "suggested_answer", "confidence"],
                      "additionalProperties": False},
        },
        "kb_gaps": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {"question": {"type": "string"},
                                     "context": {"type": "string"}},
                      "required": ["question", "context"],
                      "additionalProperties": False},
        },
        "issue_tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["resolved", "summary", "category", "faq_candidates", "kb_gaps", "issue_tags"],
    "additionalProperties": False,
}

ANALYSIS_PROMPT = """你是售后知识运营分析师。分析下面这段已结束的客服会话，输出 JSON：
- resolved：客户问题是否被解决（转人工、明确未解决、知识库无答案视为未解决）
- summary：一句话会话摘要
- category：问题所属知识分类
- faq_candidates：值得沉淀进知识库的新问答对（问题概括为通用问法，答案基于会话中验证有效的回复；已是常识或过于个案的不要提取；最多2条）
- kb_gaps：客户问了但现有知识没能回答的问题（知识缺口；最多2条）
- issue_tags：问题标签，格式"产品/主题-症状"，如"扫地机器人-不开机"、"退货政策"；最多3个

会话内容：
"""


class AnthropicClient:
    def __init__(self):
        self._client = anthropic.Anthropic(api_key=settings.api_key)
        self._async_client = anthropic.AsyncAnthropic(api_key=settings.api_key)

    async def stream_turn(self, system: str, messages: list[dict],
                          tools: list[dict], *, mock_state: dict | None = None
                          ) -> AsyncIterator[LLMEvent]:
        async with self._async_client.messages.stream(
            model=settings.model,
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            tools=tools,
            messages=messages,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        yield ToolUseStart(id=block.id, name=block.name)
                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield TextDelta(event.delta.text)
            final = await stream.get_final_message()
        yield TurnEnd(
            stop_reason=final.stop_reason or "end_turn",
            content_blocks=[b.model_dump(exclude_none=True) for b in final.content],
            usage_in=final.usage.input_tokens,
            usage_out=final.usage.output_tokens,
        )

    def analyze_image(self, image_b64: str, mime: str, hint: str = "") -> str:
        response = self._client.messages.create(
            model=settings.model, max_tokens=800,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime,
                                             "data": image_b64}},
                {"type": "text", "text":
                 "你是售后技术专员。请观察这张客户上传的照片，输出：①看到的产品/部位；"
                 "②可见异常/错误信息；③初步故障判断。简洁准确，不编造。"
                 + (f"\n客户描述：{hint}" if hint else "")},
            ]}])
        return next((b.text for b in response.content if b.type == "text"), "").strip()

    def ocr_image(self, image_b64: str, mime: str = "image/png") -> str:
        response = self._client.messages.create(
            model=settings.model, max_tokens=4000,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime,
                                             "data": image_b64}},
                {"type": "text", "text": "请逐行输出图中的全部文字内容，保持原有顺序，不要遗漏，不要添加解释。"},
            ]}])
        return next((b.text for b in response.content if b.type == "text"), "").strip()

    def qa_review(self, transcript: str) -> dict:
        schema = {
            "type": "object",
            "properties": {
                "score": {"type": "integer"},
                "dimensions": {"type": "object",
                               "properties": {"服务态度": {"type": "integer"},
                                              "专业准确": {"type": "integer"},
                                              "解决效率": {"type": "integer"}},
                               "required": ["服务态度", "专业准确", "解决效率"],
                               "additionalProperties": False},
                "issues": {"type": "array", "items": {"type": "string"}},
                "suggestion": {"type": "string"},
            },
            "required": ["score", "dimensions", "issues", "suggestion"],
            "additionalProperties": False,
        }
        response = self._client.messages.create(
            model=settings.model, max_tokens=800,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content":
                       "你是客服质检专员。评估这段售后对话中客服的服务质量（score 总分0-100，"
                       "dimensions 三维度各0-100，issues 最多3条，suggestion 一句改进建议）：\n\n"
                       + transcript[:8000]}])
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text)

    def suggest_reply(self, transcript: str) -> str:
        response = self._client.messages.create(
            model=settings.model, max_tokens=600,
            messages=[{"role": "user", "content":
                       "你是资深售后客服导师。下面是一段客服对话，请为人工客服拟一条可直接发送的回复"
                       "（简体中文，称呼\"您\"，先共情后解决，具体可执行，不超过150字，只输出回复正文）：\n\n"
                       + transcript[:6000]}])
        return next((b.text for b in response.content if b.type == "text"), "").strip()

    def digest_manual(self, title: str, manual_text: str) -> list[dict]:
        schema = {
            "type": "object",
            "properties": {
                "faqs": {
                    "type": "array",
                    "items": {"type": "object",
                              "properties": {"question": {"type": "string"},
                                             "suggested_answer": {"type": "string"},
                                             "category": {"type": "string"},
                                             "confidence": {"type": "number"}},
                              "required": ["question", "suggested_answer", "category", "confidence"],
                              "additionalProperties": False},
                },
            },
            "required": ["faqs"], "additionalProperties": False,
        }
        prompt = (
            f"你是售后知识运营。通读产品手册《{title}》，提炼客户最可能咨询的 6-10 条问答对"
            "（优先：高频操作、易错点、保养周期、安全注意）。question 用客户口吻的通用问法，"
            "suggested_answer 基于手册原文、具体可执行，category 取值：产品使用/故障排查/退换货政策/保修条款/物流/其他。\n\n"
            f"手册内容：\n{manual_text}")
        response = self._client.messages.create(
            model=settings.model, max_tokens=4096,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": prompt}])
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text).get("faqs", [])

    def analyze_conversation(self, transcript: str) -> AnalysisResult:
        response = self._client.messages.create(
            model=settings.model,
            max_tokens=4096,
            output_config={"format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA}},
            messages=[{"role": "user", "content": ANALYSIS_PROMPT + transcript[:20000]}],
        )
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        return AnalysisResult(
            resolved=bool(data.get("resolved")),
            summary=data.get("summary", ""),
            category=data.get("category", "其他"),
            faq_candidates=data.get("faq_candidates", []),
            kb_gaps=data.get("kb_gaps", []),
            issue_tags=data.get("issue_tags", []),
        )


def get_llm_client():
    """按配置返回 LLM 实现（模块级单例）：anthropic / openai兼容 / mock"""
    global _instance
    if _instance is None:
        if settings.provider == "mock":
            from .mock_client import MockClient
            _instance = MockClient()
        elif settings.provider == "openai":
            from .openai_compat_client import OpenAICompatClient
            _instance = OpenAICompatClient()
        else:
            _instance = AnthropicClient()
    return _instance


_instance = None
