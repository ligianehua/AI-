import uuid
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from app.core.db import SessionDep
from app.core.exceptions import NotAuthenticatedError
from app.core.security import decode_access_token
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: SessionDep,
) -> User:
    if credentials is None:
        raise NotAuthenticatedError("未登录或令牌缺失")
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise NotAuthenticatedError("令牌无效或已过期") from exc
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except ValueError as exc:
        raise NotAuthenticatedError("令牌无效或已过期") from exc
    user = await session.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None or not user.is_active:
        raise NotAuthenticatedError("账号不存在或已停用")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
