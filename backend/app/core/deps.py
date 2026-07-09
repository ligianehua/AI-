from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import NotAuthenticatedError
from app.core.security import decode_access_token
from app.schemas.auth import CurrentUser
from app.services import auth_service

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if credentials is None:
        raise NotAuthenticatedError("未登录或令牌缺失")
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise NotAuthenticatedError("令牌无效或已过期") from exc
    email = payload.get("sub")
    if not isinstance(email, str):
        raise NotAuthenticatedError("令牌无效或已过期")
    return await auth_service.get_user_by_email(email)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
