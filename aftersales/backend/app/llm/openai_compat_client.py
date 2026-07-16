"""OpenAI 兼容接口的 LLM 客户端（适配国产模型中转站：Qwen/GLM/DeepSeek 等）。

对 engine 暴露与 Anthropic 客户端完全相同的事件流接口；
内部把 Anthropic 风格的 content blocks 与 OpenAI chat.completions 格式互相转换。
"""
import json
import re
import uuid
from typing import AsyncIterator

from openai import AsyncOpenAI, OpenAI

from ..config import settings
from .base import AnalysisResult, LLMEvent, TextDelta, ToolUseStart, TurnEnd

ANALYSIS_PROMPT = """你是售后知识运营分析师。分析下面这段已结束的客服会话，只输出一个 JSON 对象（不要输出任何其他文字、不要用代码块包裹），字段如下：
- resolved (bool)：客户问题是否被解决（转人工、明确未解决、知识库无答案视为未解决）
- summary (string)：一句话会话摘要
- category (string)：问题所属知识分类，取值只能是：产品使用/故障排查/退换货政策/保修条款/物流/其他
- faq_candidates (array)：值得沉淀进知识库的新问答对，每项 {question, suggested_answer, confidence(0-1)}；问题概括为通用问法，答案基于会话中验证有效的回复；过于个案的不要提取；最多2条
- kb_gaps (array)：客户问了但现有知识没能回答的问题，每项 {question, context}；最多2条
- issue_tags (array of string)：问题标签，格式"产品/主题-症状"，如"扫地机器人-不开机"、"退货政策"；最多3个

会话内容：
"""


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    return [{
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
        },
    } for t in tools]


def _to_openai_messages(system: str, messages: list[dict]) -> list[dict]:
    """Anthropic 风格 messages -> OpenAI 格式（tool_result -> role=tool）"""
    out: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        role, content = m.get("role"), m.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            continue
        if role == "user":
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b.get("content", "")
                    if isinstance(c, list):
                        c = "".join(x.get("text", "") for x in c if isinstance(x, dict))
                    out.append({"role": "tool", "tool_call_id": b.get("tool_use_id", ""),
                                "content": str(c)})
            texts = [b.get("text", "") for b in content
                     if isinstance(b, dict) and b.get("type") == "text"]
            if texts:
                out.append({"role": "user", "content": "\n".join(texts)})
        else:  # assistant
            text = "".join(b.get("text", "") for b in content
                           if isinstance(b, dict) and b.get("type") == "text")
            tool_calls = [{
                "id": b.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {"name": b.get("name", ""),
                             "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False)},
            } for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
            msg: dict = {"role": "assistant", "content": text or None}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            out.append(msg)
    return out


def _parse_json_loose(text: str) -> dict:
    """宽松解析模型输出的 JSON（容忍代码块包裹/前后杂讯）"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


class OpenAICompatClient:
    def __init__(self):
        self._client = OpenAI(api_key=settings.openai_api_key,
                              base_url=settings.openai_base_url, timeout=120)
        self._async_client = AsyncOpenAI(api_key=settings.openai_api_key,
                                         base_url=settings.openai_base_url, timeout=120)

    async def stream_turn(self, system: str, messages: list[dict],
                          tools: list[dict], *, mock_state: dict | None = None
                          ) -> AsyncIterator[LLMEvent]:
        stream = await self._async_client.chat.completions.create(
            model=settings.model,
            max_tokens=4096,
            messages=_to_openai_messages(system, messages),
            tools=_to_openai_tools(tools),
            stream=True,
        )
        text_parts: list[str] = []
        # index -> {id, name, arguments}
        calls: dict[int, dict] = {}
        finish_reason = None
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta is not None and delta.content:
                text_parts.append(delta.content)
                yield TextDelta(delta.content)
            if delta is not None and delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index or 0
                    slot = calls.setdefault(idx, {"id": None, "name": "", "arguments": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["name"] += tc.function.name
                            yield ToolUseStart(id=slot["id"] or f"call_{idx}", name=slot["name"])
                        if tc.function.arguments:
                            slot["arguments"] += tc.function.arguments
            if choice.finish_reason:
                finish_reason = choice.finish_reason

        blocks: list[dict] = []
        full_text = "".join(text_parts)
        if full_text:
            blocks.append({"type": "text", "text": full_text})
        for idx in sorted(calls):
            slot = calls[idx]
            try:
                args = json.loads(slot["arguments"]) if slot["arguments"].strip() else {}
            except json.JSONDecodeError:
                args = {}
            blocks.append({"type": "tool_use",
                           "id": slot["id"] or f"call_{uuid.uuid4().hex[:12]}",
                           "name": slot["name"], "input": args})
        has_tools = bool(calls)
        yield TurnEnd(
            stop_reason="tool_use" if (has_tools or finish_reason == "tool_calls") else "end_turn",
            content_blocks=blocks or [{"type": "text", "text": ""}],
            usage_in=0, usage_out=len(full_text),
        )

    def analyze_image(self, image_b64: str, mime: str, hint: str = "") -> str:
        resp = self._client.chat.completions.create(
            model=settings.vision_model, max_tokens=800,
            messages=[{"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                {"type": "text", "text":
                 "你是售后技术专员。请观察这张客户上传的照片（可能是产品故障现象、错误提示、损坏部位等），"
                 "用简体中文输出：①看到了什么产品/部位；②可见的异常/错误信息（如有错误代码请原样读出）；"
                 "③初步故障判断。简洁准确，不要编造看不到的内容。"
                 + (f"\n客户描述：{hint}" if hint else "")},
            ]}])
        return (resp.choices[0].message.content or "").strip()

    def ocr_image(self, image_b64: str, mime: str = "image/png") -> str:
        resp = self._client.chat.completions.create(
            model=settings.ocr_model, max_tokens=4000,
            messages=[{"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                {"type": "text", "text": "请逐行输出图中的全部文字内容，保持原有顺序，不要遗漏，不要添加解释。"},
            ]}])
        return (resp.choices[0].message.content or "").strip()

    def qa_review(self, transcript: str) -> dict:
        prompt = (
            "你是客服质检专员。评估下面这段售后对话中客服（AI或人工）的服务质量，"
            "只输出一个 JSON 对象（无其他文字、不用代码块）：\n"
            "- score：总分 0-100\n"
            "- dimensions：{\"服务态度\": 0-100, \"专业准确\": 0-100, \"解决效率\": 0-100}\n"
            "- issues：发现的问题列表（最多3条，没有则空数组）\n"
            "- suggestion：一句改进建议\n\n对话内容：\n" + transcript[:8000])
        resp = self._client.chat.completions.create(
            model=settings.model, max_tokens=800,
            messages=[{"role": "user", "content": prompt}])
        return _parse_json_loose(resp.choices[0].message.content or "{}")

    def suggest_reply(self, transcript: str) -> str:
        resp = self._client.chat.completions.create(
            model=settings.model, max_tokens=600,
            messages=[{"role": "user", "content":
                       "你是资深售后客服导师。下面是一段客服对话，请为人工客服拟一条可直接发送的回复"
                       "（简体中文，称呼\"您\"，先共情后解决，具体可执行，不超过150字，只输出回复正文）：\n\n"
                       + transcript[:6000]}])
        return (resp.choices[0].message.content or "").strip()

    def digest_manual(self, title: str, manual_text: str) -> list[dict]:
        prompt = (
            f"你是售后知识运营。通读下面的产品手册《{title}》，提炼客户最可能咨询的问答对。\n"
            "只输出一个 JSON 数组（不要其他文字、不要代码块），每项字段：\n"
            "- question：客户口吻的通用问法（如\"扫地机器人多久清理一次滤网？\"）\n"
            "- suggested_answer：基于手册原文的准确回答，具体、可执行\n"
            "- category：产品使用/故障排查/退换货政策/保修条款/物流/其他 之一\n"
            "- confidence：0-1\n"
            "提炼 6-10 条最有价值的（优先：高频操作、易错点、保养周期、安全注意）。\n\n"
            f"手册内容：\n{manual_text}")
        resp = self._client.chat.completions.create(
            model=settings.model, max_tokens=3000,
            messages=[{"role": "user", "content": prompt}])
        text = resp.choices[0].message.content or "[]"
        text = text.strip()
        m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
        if m:
            text = m.group(1)
        start, end = text.find("["), text.rfind("]")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        try:
            data = json.loads(text)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    def analyze_conversation(self, transcript: str) -> AnalysisResult:
        resp = self._client.chat.completions.create(
            model=settings.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": ANALYSIS_PROMPT + transcript[:16000]}],
        )
        data = _parse_json_loose(resp.choices[0].message.content or "{}")
        return AnalysisResult(
            resolved=bool(data.get("resolved")),
            summary=str(data.get("summary", "")),
            category=str(data.get("category", "其他")),
            faq_candidates=list(data.get("faq_candidates") or []),
            kb_gaps=list(data.get("kb_gaps") or []),
            issue_tags=[str(t) for t in (data.get("issue_tags") or [])],
        )
