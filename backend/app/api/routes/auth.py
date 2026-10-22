"""注册、登录及当前用户接口；响应始终使用统一外壳，不返回密码摘要。"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_auth_service, get_current_user
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisteredUser,
    RegisterRequest,
    UserInfo,
)
from app.schemas.response import ApiResponse, success
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=ApiResponse[RegisteredUser])
async def register(
    body: RegisterRequest, service: Annotated[AuthService, Depends(get_auth_service)]
):
    """创建普通用户或仅记录身份的超级管理员；成功后仍需单独登录。"""
    return success(await service.register(body))


@router.post("/login", response_model=ApiResponse[LoginResponse])
async def login(
    body: LoginRequest, service: Annotated[AuthService, Depends(get_auth_service)]
):
    """验证用户名密码并返回短期访问令牌，不创建刷新令牌或登录会话。"""
    return success(await service.login(body))


@router.get("/me", response_model=ApiResponse[UserInfo])
async def me(user: Annotated[User, Depends(get_current_user)]):
    """返回 JWT 对应的当前有效用户，便于客户端恢复登录身份。"""
    return success(UserInfo.model_validate(user))
