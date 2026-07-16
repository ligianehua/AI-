"""FastAPI 应用入口（含角色化鉴权与主动提醒定时任务）"""
import asyncio

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import SessionLocal, init_db
from .routers import (
    analytics,
    auth,
    channel,
    chat,
    conversations,
    export,
    kb,
    learning,
    manuals,
    meta,
    qa,
    reminders,
    rma,
    satisfaction,
    tickets,
    workbench,
)
from .services.auth_service import get_current_staff, require_roles, seed_staff

app = FastAPI(title="AI售后助手", version="2.0.0")

# 公开 / 自带鉴权的路由
app.include_router(auth.router)
app.include_router(meta.router)
app.include_router(chat.router)           # 客户鉴权在端点内
app.include_router(conversations.router)  # 双身份鉴权在端点内
app.include_router(satisfaction.router)   # 双身份鉴权在端点内
app.include_router(reminders.router)      # 双身份鉴权在端点内
app.include_router(channel.router)        # 渠道密钥鉴权在端点内

# 客服域（agent / admin）
for r in (tickets, rma, workbench):
    app.include_router(r.router, dependencies=[Depends(require_roles("agent"))])

# 知识运营域（ops / admin）
for r in (kb, manuals, learning):
    app.include_router(r.router, dependencies=[Depends(require_roles("ops"))])

# 数据分析 / 质检 / 导出（任意员工）
for r in (analytics, qa, export):
    app.include_router(r.router, dependencies=[Depends(get_current_staff)])


@app.on_event("startup")
def _startup():
    init_db()
    db = SessionLocal()
    try:
        seed_staff(db)
    finally:
        db.close()
    # 主动提醒：启动后延迟首扫，之后每 30 分钟一轮；学习分析每小时检查自动运行
    from .services import reminder_service
    loop = asyncio.get_event_loop()
    loop.create_task(reminder_service.periodic_scan())
    loop.create_task(reminder_service.auto_learning_loop())


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(settings.frontend_dir / "index.html")


@app.get("/admin", include_in_schema=False)
def admin():
    return FileResponse(settings.frontend_dir / "admin.html")


settings.uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.uploads_dir), name="uploads")
app.mount("/static", StaticFiles(directory=settings.frontend_dir), name="static")
