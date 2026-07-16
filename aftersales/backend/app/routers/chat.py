"""聊天 SSE 路由（客户鉴权；支持图片上传诊断；人工接管模式下不走 LLM）"""
import base64
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..agent.engine import chat_stream
from ..config import settings
from ..database import get_db
from ..llm.anthropic_client import get_llm_client
from ..models import Conversation, Customer, Message
from ..services.auth_service import get_current_customer

router = APIRouter(prefix="/api/chat", tags=["chat"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_MIMES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


class ChatRequest(BaseModel):
    conversation_id: int
    message: str = ""
    image_base64: str | None = None   # 可带 data URL 前缀
    image_mime: str = "image/jpeg"


def _save_image(req: ChatRequest) -> tuple[str, str, str]:
    """校验并保存上传图片，返回 (文件名, 纯base64, mime)"""
    raw = req.image_base64 or ""
    mime = req.image_mime
    if raw.startswith("data:"):
        try:
            head, raw = raw.split(",", 1)
            mime = head.split(";")[0][5:]
        except ValueError:
            raise HTTPException(400, "图片数据格式错误")
    if mime not in ALLOWED_MIMES:
        raise HTTPException(400, "仅支持 JPG/PNG/WebP 图片")
    try:
        data = base64.b64decode(raw)
    except Exception:
        raise HTTPException(400, "图片数据解码失败")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "图片超过 5MB 限制")
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ALLOWED_MIMES[mime]}"
    (settings.uploads_dir / name).write_bytes(data)
    return name, raw, mime


@router.post("/stream")
async def stream(req: ChatRequest, db: Session = Depends(get_db),
                 customer: Customer = Depends(get_current_customer)):
    conv = db.query(Conversation).get(req.conversation_id)
    if not conv or conv.customer_id != customer.id:
        raise HTTPException(404, "会话不存在")
    if conv.status == "closed":
        raise HTTPException(409, "会话已关闭，请新建会话")
    text = req.message.strip()
    if not text and not req.image_base64:
        raise HTTPException(400, "消息不能为空")

    image_name = image_b64 = image_mime = None
    if req.image_base64:
        image_name, image_b64, image_mime = _save_image(req)

    if conv.mode == "human":
        # 人工接管中：只落库转发给客服，不调用 AI
        db.add(Message(conversation_id=conv.id, role="user", display_text=text,
                       image_path=image_name))
        db.commit()

        async def human_ack():
            yield ("event: meta\ndata: " +
                   json.dumps({"conversation_id": conv.id, "mode": "human"},
                              ensure_ascii=False) + "\n\n")
            yield "event: done\ndata: {}\n\n"
        return StreamingResponse(human_ack(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    # 图像分析（视觉模型），结果作为模型侧附加上下文
    api_suffix = ""
    if image_b64:
        llm = get_llm_client()
        try:
            diagnosis = llm.analyze_image(image_b64, image_mime, hint=text)
        except Exception as e:
            diagnosis = f"（图像分析失败：{e}）"
        api_suffix = ("\n\n[系统提示：客户随本条消息上传了一张故障照片，"
                      "以下是图像分析结果，请结合它判断故障并继续排查流程]\n" + diagnosis)

    return StreamingResponse(
        chat_stream(db, conv, customer, text, api_suffix=api_suffix,
                    image_path=image_name),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
