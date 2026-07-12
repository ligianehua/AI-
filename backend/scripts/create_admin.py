"""生产初始化 admin 账号（幂等：邮箱已存在则跳过）。

用法：
    uv run python -m scripts.create_admin <email> <password> [姓名]
或走环境变量（docker 里方便）：
    INIT_ADMIN_EMAIL / INIT_ADMIN_PASSWORD / INIT_ADMIN_NAME
"""

import asyncio
import os
import sys

from sqlalchemy import select

from app.core.db import get_engine, get_sessionmaker
from app.core.security import hash_password
from app.models.enums import Role
from app.models.user import User


async def main() -> None:
    email = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("INIT_ADMIN_EMAIL")
    password = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("INIT_ADMIN_PASSWORD")
    name = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("INIT_ADMIN_NAME", "系统管理员")
    if not email or not password:
        print("用法：uv run python -m scripts.create_admin <email> <password> [姓名]")
        sys.exit(1)
    if len(password) < 8:
        print("密码至少 8 位")
        sys.exit(1)

    async with get_sessionmaker()() as session:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing:
            print(f"用户 {email} 已存在（role={existing.role}），跳过")
        else:
            session.add(
                User(
                    name=name,
                    email=email,
                    hashed_password=hash_password(password),
                    role=Role.ADMIN,
                    is_active=True,
                )
            )
            await session.commit()
            print(f"管理员 {email} 创建成功")
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())
