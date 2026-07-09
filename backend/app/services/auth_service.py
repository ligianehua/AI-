"""认证服务。

M0 阶段没有 users 表（M1 交付），登录校验对象是 .env 里配置的引导管理员账号。
M1 落库后本服务改为查 users 表，接口签名保持不变。
"""

from functools import lru_cache

from app.core.config import get_settings
from app.core.exceptions import InvalidCredentialsError
from app.core.security import create_access_token, hash_password, verify_password
from app.schemas.auth import CurrentUser, TokenResponse


@lru_cache
def _bootstrap_password_hash() -> str:
    return hash_password(get_settings().admin_password)


def _bootstrap_user() -> CurrentUser:
    return CurrentUser(email=get_settings().admin_email, name="管理员", role="admin")


async def authenticate(email: str, password: str) -> TokenResponse:
    settings = get_settings()
    if email != settings.admin_email or not verify_password(password, _bootstrap_password_hash()):
        raise InvalidCredentialsError("邮箱或密码错误")
    user = _bootstrap_user()
    token = create_access_token(subject=user.email, extra={"role": user.role, "name": user.name})
    return TokenResponse(access_token=token)


async def get_user_by_email(email: str) -> CurrentUser:
    if email != get_settings().admin_email:
        raise InvalidCredentialsError("用户不存在")
    return _bootstrap_user()
