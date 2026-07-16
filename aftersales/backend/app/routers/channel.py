"""通用渠道 OpenAPI：供外部系统（微信网关/APP/小程序服务端）以同步方式接入 AI 客服。

鉴权：请求头 X-Channel-Key == 配置的 CHANNEL_API_KEY（.env，留空则本接口关闭）。
外部用户以 external_user_id 标识，自动映射为客户档案（phone 字段存 ch:<id>）。
"""
import json

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..agent.engine import chat_stream
from ..config import settings
from ..database import get_db
from ..models import Conversation, Customer, Message

router = APIRouter(prefix="/api/channel", tags=["channel"])


def _check_key(x_channel_key: str | None = Header(None)):
    if not settings.channel_api_key:
        raise HTTPException(403, "渠道接口未启用（请在 .env 配置 CHANNEL_API_KEY）")
    if x_channel_key != settings.channel_api_key:
        raise HTTPException(401, "渠道密钥无效")


class ChannelMessage(BaseModel):
    external_user_id: str          # 外部渠道用户标识（如微信 openid）
    message: str
    name: str = ""                 # 首次出现时用于建档
    channel: str = "openapi"       # 渠道名，记录在会话上
    new_conversation: bool = False  # true=强制开新会话


@router.post("/message", dependencies=[Depends(_check_key)])
async def channel_message(req: ChannelMessage, db: Session = Depends(get_db)):
    text = req.message.strip()
    if not text:
        raise HTTPException(400, "消息不能为空")
    ext = req.external_user_id.strip()
    if not ext:
        raise HTTPException(400, "external_user_id 必填")

    # 外部用户 -> 客户档案
    phone_key = f"ch:{ext}"[:20]
    customer = db.query(Customer).filter(Customer.phone == phone_key).first()
    if not customer:
        customer = Customer(name=(req.name or f"渠道用户{ext[-4:]}")[:50],
                            phone=phone_key, level="普通")
        db.add(customer)
        db.commit()

    # 复用最近的进行中会话，或新建
    conv = None
    if not req.new_conversation:
        conv = db.query(Conversation).filter(
            Conversation.customer_id == customer.id,
            Conversation.status == "active").order_by(Conversation.id.desc()).first()
    if conv is None:
        conv = Conversation(customer_id=customer.id, channel=req.channel[:10])
        db.add(conv)
        db.commit()

    # 人工接管中：仅转达
    if conv.mode == "human":
        db.add(Message(conversation_id=conv.id, role="user", display_text=text))
        db.commit()
        return {"conversation_id": conv.id, "mode": "human", "reply": None,
                "message": "会话由人工客服服务中，消息已转达"}

    # 跑 agent 循环，聚合 SSE 事件为一次性回复
    reply_parts, tools, cards, error = [], [], [], None
    async for sse_chunk in chat_stream(db, conv, customer, text):
        event, data = _parse_sse(sse_chunk)
        if event == "text_delta":
            reply_parts.append(data.get("text", ""))
        elif event == "tool_end":
            tools.append({"name": data.get("name"), "label": data.get("label"),
                          "ok": data.get("ok")})
        elif event == "card":
            cards.append(data)
        elif event == "error":
            error = data.get("message")
    if error:
        raise HTTPException(502, error)
    return {"conversation_id": conv.id, "mode": "ai",
            "reply": "".join(reply_parts), "tools": tools, "cards": cards}


def _parse_sse(chunk: str) -> tuple[str, dict]:
    event, data = "", {}
    for line in chunk.split("\n"):
        if line.startswith("event: "):
            event = line[7:].strip()
        elif line.startswith("data: "):
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                pass
    return event, data
