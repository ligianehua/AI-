"""AI售后助手 启动入口：初始化数据库 -> 播种演示数据 -> 启动服务"""
import socket

import uvicorn

from backend.app.config import settings
from backend.app.database import init_db
from backend.app.seed.seed import seed_if_empty


def pick_port(preferred: int) -> int:
    """优先使用配置端口，被占用时自动换一个空闲端口"""
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", preferred))
        return preferred
    except OSError:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        print(f"  端口 {preferred} 被占用，已自动改用端口 {port}")
        return port


def main():
    init_db()
    seed_if_empty()
    port = pick_port(settings.port)
    print("\n  AI售后助手已启动")
    print(f"  客户聊天页:  http://127.0.0.1:{port}/")
    print(f"  管理控制台:  http://127.0.0.1:{port}/admin")
    print(f"  运行模式:    {'演示模式(MOCK)' if settings.is_mock else '真实API - ' + settings.model}\n")
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
