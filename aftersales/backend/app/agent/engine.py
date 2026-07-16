"""Agent 引擎：多轮工具调用循环 + SSE 事件产出。真实/Mock LLM 共用。

SSE 事件（JSON 行）：
  meta        {conversation_id, message_id?}
  text_delta  {text}
  tool_start  {name, label}
  tool_end    {name, label, ok, summary}
  card        {kind, no, title, status}      # 工单/RMA 卡片
  done        {message_id, usage_in, usage_out}
  error       {message}
"""
import json
from datetime import datetime
from typing import AsyncIterator

from sqlalchemy.orm import Session

from ..llm.anthropic_client import get_llm_client
from ..llm.base import TextDelta, ToolUseStart, TurnEnd
from ..models import Conversation, Customer, Message
from .prompts import SYSTEM_PROMPT, build_context_message
from .tool_defs import TOOL_LABELS, TOOLS
from .tool_exec import ToolContext, run_tool

MAX_LOOPS = 8


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _load_mock_state(conv: Conversation) -> dict:
    try:
        payload = json.loads(conv.summary or "{}")
        return payload.get("_mock_state", {})
    except (json.JSONDecodeError, AttributeError):
        return {}


def _save_mock_state(conv: Conversation, state: dict):
    try:
        payload = json.loads(conv.summary or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except json.JSONDecodeError:
        payload = {}
    payload["_mock_state"] = state
    conv.summary = json.dumps(payload, ensure_ascii=False)


def rebuild_api_messages(db: Session, conversation_id: int) -> list[dict]:
    """从历史消息的 raw_blocks 重建 API messages 数组。

    assistant 行的 raw_blocks 存的是该轮产生的完整消息序列
    [{"role":"assistant","content":[...]},{"role":"user","content":[tool_results]},...]
    （thinking/tool 块原样保留，tool_result 保持在 user 角色，符合 API 规范）。
    user 行的 raw_blocks 存的是发送给 API 的内容（字符串）。
    """
    rows = db.query(Message).filter(Message.conversation_id == conversation_id) \
        .order_by(Message.id).all()
    out: list[dict] = []
    for m in rows:
        if m.role == "notice":  # 系统提示条（客服接入/退出等）不进模型上下文
            continue
        if m.raw_blocks:
            try:
                parsed = json.loads(m.raw_blocks)
            except json.JSONDecodeError:
                parsed = m.display_text
        else:
            parsed = m.display_text
        if (isinstance(parsed, list) and parsed
                and all(isinstance(x, dict) and "role" in x for x in parsed)):
            out.extend(parsed)  # 一轮内的多条 API 消息
        else:
            out.append({"role": m.role, "content": parsed})
    return out


async def chat_stream(db: Session, conversation: Conversation, customer: Customer,
                      user_text: str, *, api_suffix: str = "",
                      image_path: str | None = None) -> AsyncIterator[str]:
    """处理一条用户消息：落库 -> agent 循环 -> SSE 输出 -> 结果落库

    api_suffix：只给模型看的附加上下文（如图像分析结果），不进展示文本。
    """
    llm = get_llm_client()
    mock_state = _load_mock_state(conversation)

    # 历史（不含本条）
    api_messages = rebuild_api_messages(db, conversation.id)

    # 动态上下文注入到首条用户消息
    if not api_messages:
        prefix = build_context_message(customer.name, customer.level,
                                       datetime.now().strftime("%Y-%m-%d %H:%M"))
        content_for_api = prefix + user_text + api_suffix
        if conversation.title == "新会话":
            conversation.title = (user_text or "图片咨询")[:40]
    else:
        content_for_api = user_text + api_suffix

    # 用户消息落库
    user_msg = Message(conversation_id=conversation.id, role="user",
                       display_text=user_text, image_path=image_path,
                       raw_blocks=json.dumps(content_for_api, ensure_ascii=False))
    db.add(user_msg)
    db.commit()

    api_messages.append({"role": "user", "content": content_for_api})
    yield _sse("meta", {"conversation_id": conversation.id})

    full_text_parts: list[str] = []
    tool_badges: list[dict] = []
    total_in = total_out = 0
    turn_messages: list[dict] = []  # 本轮产生的完整 API 消息序列（assistant + tool_result user）

    try:
        for _ in range(MAX_LOOPS):
            turn_end: TurnEnd | None = None
            pending_tools: list[dict] = []

            async for ev in llm.stream_turn(SYSTEM_PROMPT, api_messages, TOOLS,
                                            mock_state=mock_state):
                if isinstance(ev, TextDelta):
                    full_text_parts.append(ev.text)
                    yield _sse("text_delta", {"text": ev.text})
                elif isinstance(ev, ToolUseStart):
                    yield _sse("tool_start", {"name": ev.name,
                                              "label": TOOL_LABELS.get(ev.name, ev.name)})
                elif isinstance(ev, TurnEnd):
                    turn_end = ev

            if turn_end is None:
                break
            total_in += turn_end.usage_in
            total_out += turn_end.usage_out
            turn_messages.append({"role": "assistant", "content": turn_end.content_blocks})

            if turn_end.stop_reason != "tool_use":
                break

            # 执行本轮全部工具调用，结果合并进同一条 user 消息
            ctx = ToolContext(db, conversation, customer)
            tool_results = []
            for block in turn_end.content_blocks:
                if block.get("type") != "tool_use":
                    continue
                name, tool_input = block["name"], block.get("input") or {}
                result, is_error = run_tool(name, tool_input, ctx)
                label = TOOL_LABELS.get(name, name)
                summary = result.get("message") or ("完成" if not is_error else "失败")
                tool_badges.append({"name": name, "label": label,
                                    "ok": not is_error, "summary": summary[:120]})
                yield _sse("tool_end", {"name": name, "label": label,
                                        "ok": not is_error, "summary": summary[:120]})
                if isinstance(result.get("card"), dict):
                    yield _sse("card", result["card"])
                tool_results.append({
                    "type": "tool_result", "tool_use_id": block["id"],
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                    **({"is_error": True} if is_error else {}),
                })
            db.commit()

            api_messages.append({"role": "assistant", "content": turn_end.content_blocks})
            api_messages.append({"role": "user", "content": tool_results})
            turn_messages.append({"role": "user", "content": tool_results})
        else:
            # 超出循环上限，强制收尾
            note = "\n\n（本次处理步骤较多，如未完全解决请告诉我，我为您转接人工客服。）"
            full_text_parts.append(note)
            yield _sse("text_delta", {"text": note})

        display_text = "".join(full_text_parts)
        ai_msg = Message(
            conversation_id=conversation.id, role="assistant",
            display_text=display_text,
            raw_blocks=json.dumps(turn_messages, ensure_ascii=False, default=str),
            tool_calls=json.dumps(tool_badges, ensure_ascii=False) if tool_badges else None,
            tokens_in=total_in or None, tokens_out=total_out or None,
        )
        db.add(ai_msg)
        _save_mock_state(conversation, mock_state)
        db.commit()
        yield _sse("done", {"message_id": ai_msg.id,
                            "usage_in": total_in, "usage_out": total_out})
    except Exception as e:
        db.rollback()
        yield _sse("error", {"message": f"处理出错：{e}"})
