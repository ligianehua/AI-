from fastapi import APIRouter

from app.core.deps import CurrentUserDep
from app.schemas.auth import CurrentUser, LoginRequest, TokenResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", summary="登录，获取访问令牌")
async def login(body: LoginRequest) -> TokenResponse:
    return await auth_service.authenticate(body.email, body.password)


@router.get("/me", summary="当前登录用户信息")
async def me(current_user: CurrentUserDep) -> CurrentUser:
    return current_user
