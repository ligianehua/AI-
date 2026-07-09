from fastapi import APIRouter

from app.core.db import SessionDep
from app.core.deps import CurrentUserDep
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", summary="登录，获取访问令牌")
async def login(body: LoginRequest, session: SessionDep) -> TokenResponse:
    return await auth_service.authenticate(session, body.email, body.password)


@router.get("/me", summary="当前登录用户信息")
async def me(current_user: CurrentUserDep) -> UserOut:
    return UserOut.model_validate(current_user)
