"""认证服务：登录校验走 users 表。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidCredentialsError
from app.core.security import create_access_token, verify_password
from app.models.user import User
from app.schemas.auth import TokenResponse


async def authenticate(session: AsyncSession, email: str, password: str) -> TokenResponse:
    user = await session.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
    if user is None or not verify_password(password, user.hashed_password):
        raise InvalidCredentialsError("邮箱或密码错误")
    if not user.is_active:
        raise InvalidCredentialsError("账号已停用")
    return TokenResponse(access_token=create_access_token(subject=str(user.id)))
